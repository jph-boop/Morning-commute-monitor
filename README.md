# Commute Train Monitor Agent 🚆

An automated, serverless agent that monitors a multi-leg rail commute and sends instant, deduplicated Telegram alerts for delays, cancellations, and next-available alternative trains during morning commute windows.

Powered by **GitHub Actions** and the official **Rail Data Marketplace (RDM) Live Departure Board API**.

---

## 🌟 Features

- **Multi-Leg Commute Monitoring:** Checks multiple journey legs independently using configurable origin and destination codes.
- **Sub-2-Minute Polling:** Bypasses GitHub Actions' standard 5-minute cron limitation by running an in-job continuous loop that checks for updates every 90 seconds.
- **Smart Alert Deduplication:** Prevents chat spam by tracking alerted train IDs in memory—sending new notifications only when disruption states change.
- **Explicit Delay Detection:** Flags minor delays ($\ge$ 1 minute) by calculating exact time deltas between scheduled and expected departure times.
- **Cancellation Alternative Lookup:** Automatically scans remaining services upon a cancellation to notify you of the next available operational train, its expected status, and platform.
- **Zero Personal Data:** Fully anonymized via environment variables and GitHub Secrets, allowing the repository to be public safely without exposing personal travel routes.
- **Instant Telegram Alerts:** Sends formatted markdown alerts directly to your Telegram chat.

---

## 📁 Repository Structure

```text
Train-monitoring-agent/
│
├── .github/
│   └── workflows/
│       └── check_train.yml            # GitHub Actions workflow (continuous loop scheduler)
│
├── morning_train_monitor.py            # Core monitoring script with loop, delay, and alternative-train logic
└── README.md                          # Documentation
