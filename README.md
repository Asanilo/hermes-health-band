# hermes-health-band

**Hermes Agent plugin** — read HUAWEI Band 8 health data (heart rate, steps,
SpO2, sleep, stress, battery) synced via Gadgetbridge.

## Prerequisites

- [Hermes Agent](https://hermes-agent.nousresearch.com) installed
- HUAWEI Band 8 paired with [Gadgetbridge](https://gadgetbridge.org/) on an Android phone
- Gadgetbridge DB synced to your computer (via Syncthing or manual copy)

## Installation

```bash
git clone https://github.com/Asanilo/hermes-health-band.git
cd hermes-health-band

# 1. Copy plugin to Hermes
cp -r health_band ~/.hermes/plugins/health-band/

# 2. Initialize data directory
python3 scripts/parse_gadgetbridge_summary.py --init

# 3. Place Gadgetbridge.db in ~/.hermes/health_band/data/
# (from your phone's Gadgetbridge export)

# 4. Parse and verify
python3 scripts/parse_gadgetbridge_summary.py --once

# 5. Restart Hermes gateway
systemctl --user restart hermes-gateway
```

## Usage

The plugin registers a single tool `health_band`:

| Action | Description |
|--------|-------------|
| `hear_my_heart` | Heart rate time series (default) |
| `summary` | Today's health summary |
| `sleep` | Sleep data |
| `history_dates` | List available historical dates |
| `all` | All data combined |

All actions accept an optional `date` parameter (`YYYY-MM-DD`).
Defaults to today when omitted.

## Data sync

Two modes:

### Cron (recommended)
```bash
# Run every 15 minutes
crontab -e
*/15 * * * * cd ~/.hermes/health_band && python3 scripts/parse_gadgetbridge_summary.py --skip-if-unchanged
```

### Watch (background daemon)
```bash
python3 scripts/watch_gadgetbridge_sync.py
```

## How it works

```
Gadgetbridge (phone) → Syncthing → ~/.hermes/health_band/data/Gadgetbridge.db
                                         ↓
                              parse_gadgetbridge_summary.py
                                         ↓
                              ~/.hermes/health_band/derived/*.json
                                         ↓
                              health_band tool in Hermes
```

## Plugin structure

```
hermes-health-band/
├── health_band/
│   ├── __init__.py
│   └── tools.py
├── scripts/
│   ├── parse_gadgetbridge_summary.py
│   └── watch_gadgetbridge_sync.py
├── sample_data/
│   └── derived/example-summary.json
├── docs/
│   └── debugging.md
├── plugin.yaml
├── pyproject.toml
└── README.md
```

## License

MIT
