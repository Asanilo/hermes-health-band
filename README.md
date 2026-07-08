<picture>
  <source media="(prefers-color-scheme: dark)" srcset="https://img.shields.io/badge/hermes--plugin-health--band-8b5cf6?style=for-the-badge&logo=data:image/svg+xml;base64,PHN2ZyB4bWxucz0iaHR0cDovL3d3dy53My5vcmcvMjAwMC9zdmciIHdpZHRoPSIyNCIgaGVpZ2h0PSIyNCIgdmlld0JveD0iMCAwIDI0IDI0IiBmaWxsPSJub25lIiBzdHJva2U9IndoaXRlIiBzdHJva2Utd2lkdGg9IjIiIHN0cm9rZS1saW5lY2FwPSJyb3VuZCIgc3Ryb2tlLWxpbmVqb2luPSJyb3VuZCI+PHBhdGggZD0iTTE5IDE0YzEuNDktMS40NiAyLjUtMy4zNSAyLjUtNS41IDAtMi40OS0yLjAxLTQuNS00LjUtNC41UzEyLjUgNi4wMSAxMi41IDguNWMwIDIuMTUgMS4wMSA0LjA0IDIuNSA1LjV2NWMwIC44My42NyAxLjUgMS41IDEuNXMxLjUtLjY3IDEuNS0xLjV2LTV6Ii8+PHBhdGggZD0iTTEyIDIyaC01Yy0uODMgMC0xLjUtLjY3LTEuNS0xLjV2LTUuNWMtMS40OS0xLjQ2LTIuNS0zLjM1LTIuNS01LjVDMyA3LjAxIDUuMDEgNSA3LjUgNVMxMiA3LjAxIDEyIDkuNWMwIDIuMTUtMS4wMSA0LjA0LTIuNSA1LjV2NS41YzAgLjgzLS42NyAxLjUtMS41IDEuNXoiLz48L3N2Zz4=">
  <img alt="hermes-health-band" src="https://img.shields.io/badge/hermes--plugin-health--band-8b5cf6?style=for-the-badge">
</picture>

# hermes-health-band 🩺⌚

> **Hermes Agent plugin** — read health data from **any** Gadgetbridge-compatible
> smart band: heart rate, steps, SpO₂, sleep, stress, battery.

---

## 📋 Prerequisites

| What | How |
|------|-----|
| 🤖 **Hermes Agent** | `hermes --version` — install from [hermes-agent.nousresearch.com](https://hermes-agent.nousresearch.com) |
| ⌚ **Smart band** | Paired via [Gadgetbridge](https://gadgetbridge.org/) on Android |
| 📡 **Database sync** | `Gadgetbridge.db` synced to your computer (Syncthing / manual copy) |

---

## 🚀 Quick start

```bash
# 1. Clone & install plugin
git clone https://github.com/Asanilo/hermes-health-band.git
cd hermes-health-band
cp -r health_band ~/.hermes/plugins/health-band/

# 2. Create data directory
python3 scripts/parse_gadgetbridge_summary.py --init

# 3. Place your Gadgetbridge.db → ~/.hermes/health_band/data/
#    (sync from phone via Syncthing or copy manually)

# 4. Parse & verify
python3 scripts/parse_gadgetbridge_summary.py --once

# 5. Restart Hermes
systemctl --user restart hermes-gateway
```

---

## 🎮 Usage

| Action | What it does |
|--------|-------------|
| `hear_my_heart` 💓 | Heart rate time series for today (or a given date) |
| `summary` 📊 | Today's health summary (steps, HR, SpO₂, battery) |
| `sleep` 🌙 | Sleep data (deep/light/REM durations, wake-ups) |
| `history_dates` 📅 | List available historical dates |
| `all` 📋 | Everything combined |

All actions accept an optional `date=YYYY-MM-DD` parameter. Defaults to today.

### Examples

```
health_band(action="summary")
health_band(action="hear_my_heart", date="2026-06-15")
health_band(action="sleep")
health_band(action="all")
```

---

## 🔄 Data pipeline

```
┌─────────────────┐     ┌──────────────────────┐     ┌──────────────────────┐
│  Gadgetbridge   │     │  Syncthing / USB      │     │  parse script         │
│  (Android)      │ ──▶ │  ~/health_band/data/  │ ──▶ │  → derived/*.json     │
│  Band 8 / Mi    │     │  Gadgetbridge.db      │     │  (auto-detect brand)  │
│  / Garmin ...   │     │                       │     │                      │
└─────────────────┘     └──────────────────────┘     └──────────┬───────────┘
                                                                │
                                                                ▼
                                                  ┌──────────────────────┐
                                                  │  health_band tool    │
                                                  │  in Hermes session   │
                                                  └──────────────────────┘
```

> 💡 **Multi-brand support** — the script auto-detects which database tables
> your band uses (Huawei, Xiaomi, Mi Band, Huami, CMF, Garmin, Pebble…).
> See [`docs/debugging.md`](docs/debugging.md) for database field details.

---

## ⏱️ Data sync modes

### Cron (recommended) ⭐

```bash
# Runs every 15 minutes, skips if DB hasn't changed
crontab -e
*/15 * * * * cd ~/.hermes/health_band && python3 scripts/parse_gadgetbridge_summary.py --skip-if-unchanged
```

### Watch daemon 🕒

```bash
python3 scripts/watch_gadgetbridge_sync.py          # continuous (30s interval)
python3 scripts/watch_gadgetbridge_sync.py --once   # one-shot (for manual runs)
```

### Init (first-time setup)

```bash
python3 scripts/parse_gadgetbridge_summary.py --init
# Creates: ~/.hermes/health_band/{data/, derived/, derived/history/}
```

### Profile support

```bash
python3 scripts/parse_gadgetbridge_summary.py --hermes-home ~/.hermes/profiles/coder
```

---

## 📁 Repo structure

```
hermes-health-band/
├── health_band/                     # 🧩 Plugin (copy to ~/.hermes/plugins/)
│   ├── __init__.py                  #   register(ctx) — Hermes entry point
│   └── tools.py                     #   health_band tool (schema + handler)
├── scripts/
│   ├── parse_gadgetbridge_summary.py  # 🔄 Parse DB → derived JSON
│   └── watch_gadgetbridge_sync.py     # 👀 Background watcher daemon
├── sample_data/derived/             # 📎 Anonymous example JSONs
│   ├── example-summary.json
│   ├── example-heart.json
│   └── example-sleep.json
├── docs/
│   └── debugging.md                 # 🔧 DB schema, SQL reference, known limits
├── plugin.yaml                      # Hermes manifest
├── pyproject.toml                   # pip installable
├── SKILL.md                         # Agent usage guide
└── README.md                        # ← you are here
```

---

## 📜 License

MIT — use freely, contribute back if you can.
