import os
import sys
import time
import argparse
from datetime import datetime
import requests

# Environmental Secrets & Credentials
NRE_TOKEN = os.getenv("NRE_TOKEN", "").strip()
TELEGRAM_TOKEN = os.getenv("TELEGRAM_TOKEN", "").strip()
TELEGRAM_CHAT_ID = os.getenv("TELEGRAM_CHAT_ID", "").strip()

# --- FULLY ANONYMIZED COMMUTE LEGS CONFIGURATION ---
LEGS = [
    {
        "name": "Commute Leg 1",
        "origin": os.getenv("LEG_1_ORIGIN", "").strip(),
        "destination": os.getenv("LEG_1_DEST", "").strip(),
        "start_time": "07:30",
        "end_time": "08:45"
    },
    {
        "name": "Commute Leg 2",
        "origin": os.getenv("LEG_2_ORIGIN", "").strip(),
        "destination": os.getenv("LEG_2_DEST", "").strip(),
        "start_time": "08:00",
        "end_time": "09:30"
    }
]

# Track alerted service IDs to prevent duplicate alerts within the same run session
ALERTED_SERVICES = set()

def send_telegram_message(message):
    """Sends a formatted notification to your Telegram chat."""
    if not TELEGRAM_TOKEN or not TELEGRAM_CHAT_ID:
        print("⚠️ Telegram credentials missing. Logging alert to console:")
        print(message)
        return False

    url = f"https://api.telegram.org/bot{TELEGRAM_TOKEN}/sendMessage"
    payload = {
        "chat_id": TELEGRAM_CHAT_ID,
        "text": message,
        "parse_mode": "Markdown"
    }
    try:
        res = requests.post(url, json=payload, timeout=10)
        if res.status_code == 200:
            print("📱 Telegram alert sent successfully!")
            return True
        else:
            print(f"❌ Failed to send Telegram message: {res.text}")
            return False
    except Exception as e:
        print(f"❌ Telegram send error: {e}")
        return False

def parse_time(time_str):
    """Parses HH:MM string into a datetime time object."""
    try:
        return datetime.strptime(time_str, "%H:%M").time()
    except Exception:
        return None

def get_delay_minutes(std_str, etd_str):
    """Calculates delay in minutes between scheduled (std) and expected (etd) time."""
    if not std_str or not etd_str or etd_str.lower() in ["on time", "cancelled", "delayed", "n/a"]:
        return 0
    try:
        fmt = "%H:%M"
        t_std = datetime.strptime(std_str, fmt)
        t_etd = datetime.strptime(etd_str, fmt)
        
        delay = int((t_etd - t_std).total_seconds() / 60)
        if delay < -1000:  # Handle midnight rollover edge cases
            delay += 1440
            
        return max(0, delay)
    except Exception:
        return 0

def check_leg_status(leg, ignore_time_limits=False):
    """Queries RDM API for a specific commute leg and returns any delay/cancellation alerts."""
    url = f"https://api1.raildata.org.uk/1010-live-departure-board-dep1_2/LDBWS/api/20220120/GetDepBoardWithDetails/{leg['origin']}"
    headers = {
        "x-apikey": NRE_TOKEN,
        "Accept": "application/json",
        "User-Agent": "Mozilla/5.0"
    }
    params = {
        "numRows": "15",
        "filterCrs": leg["destination"],
        "filterType": "to"
    }

    start_limit = parse_time(leg["start_time"])
    end_limit = parse_time(leg["end_time"])

    alerts = []

    try:
        response = requests.get(url, headers=headers, params=params, timeout=10)
        if response.status_code != 200:
            print(f"❌ API Error for {leg['origin']} ({response.status_code}): {response.text}")
            return alerts

        data = response.json()
        services = data.get("trainServices") or []

        for index, train in enumerate(services):
            service_id = train.get("serviceID") or train.get("serviceIdUnique") or f"{leg['origin']}_{train.get('std')}"
            std_str = train.get("std")
            etd_str = train.get("etd", "On time")
            platform = train.get("platform", "TBD")
            is_cancelled = train.get("isCancelled", False)

            train_time = parse_time(std_str)
            if not train_time:
                continue

            # Skip services outside time window unless testing
            if not ignore_time_limits:
                if not (start_limit <= train_time <= end_limit):
                    continue

            # Unique key for deduplication
            alert_key = f"{service_id}_{etd_str}"
            if alert_key in ALERTED_SERVICES:
                continue

            delay_mins = get_delay_minutes(std_str, etd_str)

            # Detect Cancellations & find next available alternative train
            if is_cancelled or etd_str.lower() == "cancelled":
                cancel_msg = f"❌ *CANCELLED*: {std_str} service from {leg['origin']} to {leg['destination']}."
                
                next_train_msg = ""
                for next_train in services[index + 1:]:
                    next_etd = next_train.get("etd", "On time")
                    next_is_cancelled = next_train.get("isCancelled", False)
                    
                    if not next_is_cancelled and next_etd.lower() != "cancelled":
                        next_std = next_train.get("std")
                        next_plat = next_train.get("platform", "TBD")
                        
                        if next_etd.lower() in ["on time", "n/a"]:
                            status_desc = "On time"
                        else:
                            status_desc = f"expected {next_etd}"
                            
                        next_train_msg = f"\n   ➡️ *Next available:* {next_std} ({status_desc} | Plat {next_plat})"
                        break
                
                if not next_train_msg:
                    next_train_msg = "\n   ⚠️ *No further non-cancelled services found in window.*"

                alerts.append(cancel_msg + next_train_msg)
                ALERTED_SERVICES.add(alert_key)

            # Detect Delays >= 1 Minute
            elif etd_str.lower() == "delayed" or delay_mins >= 1:
                delay_desc = f"*{delay_mins} mins late* (expected *{etd_str}*)" if delay_mins > 0 else f"expected *{etd_str}*"
                alerts.append(f"⚠️ *DELAYED*: {std_str} from {leg['origin']} is {delay_desc} (Plat {platform}).")
                ALERTED_SERVICES.add(alert_key)

    except Exception as e:
        print(f"❌ Network/Parsing error checking {leg['origin']}: {e}")

    return alerts

def run_check(ignore_time_limits=False):
    """Executes a single check pass across all configured commute legs."""
    all_disruptions = []
    for leg in LEGS:
        leg_alerts = check_leg_status(leg, ignore_time_limits=ignore_time_limits)
        if leg_alerts:
            all_disruptions.append(f"📍 *{leg['name']}*\n" + "\n".join(leg_alerts))

    if all_disruptions:
        header = "🚨 *UK Commute Disruption Alert*\n\n"
        full_message = header + "\n\n".join(all_disruptions)
        send_telegram_message(full_message)

def main():
    parser = argparse.ArgumentParser(description="Morning Train Monitor Agent")
    parser.add_argument("--test", action="store_true", help="Run in test mode")
    parser.add_argument("--loop", action="store_true", help="Run in continuous loop mode")
    parser.add_argument("--interval", type=int, default=90, help="Polling interval in seconds (default: 90)")
    parser.add_argument("--duration", type=int, default=7500, help="Total execution duration in seconds (default: 7500)")
    args = parser.parse_args()

    if args.test:
        print("🧪 RUNNING IN TEST MODE...")
        send_telegram_message("🔔 *UK Train Monitor Verification Alert*\n\nTest run initiated successfully!")
        run_check(ignore_time_limits=True)
        return

    if not NRE_TOKEN:
        print("❌ CRITICAL: NRE_TOKEN is missing!")
        sys.exit(1)

    if args.loop:
        print(f"🔄 Starting loop mode: checking every {args.interval}s for {args.duration}s...")
        start_ts = time.time()
        while time.time() - start_ts < args.duration:
            try:
                run_check()
            except Exception as e:
                print(f"⚠️ Unexpected error inside loop iteration: {e}")
            time.sleep(args.interval)
    else:
        run_check()

    # Ensure mandatory secrets/station codes are provided
    if not NRE_TOKEN:
        print("❌ CRITICAL: NRE_TOKEN is missing!")
        sys.exit(1)
        
    for leg in LEGS:
        if not leg["origin"] or not leg["destination"]:
            print(f"❌ CRITICAL: Station codes for '{leg['name']}' are missing from environment variables!")
            sys.exit(1)


if __name__ == "__main__":
    main()
