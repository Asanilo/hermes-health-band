# 调试指南

> 以下 SQL 表名是 Gadgetbridge 数据库的实际名称（`HUAWEI_*` 前缀是历史命名惯例，各品牌手环通用）。

## 0. 检查数据库新鲜度

```bash
sqlite3 ~/.hermes/health_band/data/Gadgetbridge.db "
  SELECT 'sleep' as tbl, datetime(MAX(timestamp)/1000,'unixepoch','localtime') as latest FROM HUAWEI_SLEEP_STATS_SAMPLE
  UNION ALL
  SELECT 'activity', datetime(MAX(timestamp),'unixepoch','localtime') FROM HUAWEI_ACTIVITY_SAMPLE
  UNION ALL
  SELECT 'stress', datetime(MAX(timestamp)/1000,'unixepoch','localtime') FROM HUAWEI_STRESS_SAMPLE;
"
```

If latest data is several days old → Syncthing sync is probably stalled.
Check: `journalctl --user -u syncthing --since "1 day ago" --no-pager | grep -E "Established|Lost device|connected|disconnected"`

## L1. Check script output

```bash
cd ~/.hermes/health_band
python3 scripts/parse_gadgetbridge_summary.py --date $(date +%Y-%m-%d)
cat derived/sleep.json | python3 -m json.tool | head -20
```

## Timestamp unit reference

| Table | Unit | `day_bounds` | `_safe_iso` |
|-------|------|-------------|-------------|
| `HUAWEI_ACTIVITY_SAMPLE` | seconds (10-digit) | `day_bounds_s` | no `is_ms` |
| `HUAWEI_SLEEP_STATS_SAMPLE` | ms (13-digit) | custom ms range | `is_ms=True` |
| `HUAWEI_SLEEP_STAGE_SAMPLE` | ms (13-digit) | custom prev_ms/next_ms | `is_ms=True` |
| `HUAWEI_STRESS_SAMPLE` | ms (13-digit) | `day_bounds` | `is_ms=True` |

## SQL column order

`HUAWEI_SLEEP_STATS_SAMPLE` SELECT order (must match unpacking):
```
0:TIMESTAMP 1:DEVICE_ID 2:USER_ID 3:SLEEP_SCORE 4:BED_TIME 5:WAKEUP_TIME
6:DEEP_PART 7:WAKE_COUNT 8:SLEEP_DATA_QUALITY 9:MIN_HEART_RATE
10:AVG_HEART_RATE 11:MIN_OXYGEN_SATURATION 12:AVG_OXYGEN_SATURATION
```

## Known limitations

- Some bands do not write `MIN_HEART_RATE`, `AVG_HEART_RATE`, `MIN_OXYGEN_SATURATION`, `AVG_OXYGEN_SATURATION` during sleep (all -1 in DB)
- `HEART_PULSE_SAMPLE`, `MI_BAND_ACTIVITY_SAMPLE` tables may be empty depending on band model
- `BED_TIME = -1000` means invalid (band doesn't record it)
- SCORE=-1 rows are invalid sessions — filtered out by the script
