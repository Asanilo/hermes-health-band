---
name: health-band
description: 智能手环数据查询工具，通过 Gadgetbridge 同步数据
tags: [health, wearable, gadgetbridge]
---

# health-band

智能手环数据查询工具，通过 Gadgetbridge 同步数据。

## Tool

```
health_band action=<action> date=<YYYY-MM-DD>
```

| action | 说明 |
|--------|------|
| `hear_my_heart` | 心率时序（默认） |
| `summary` | 当日健康摘要 |
| `sleep` | 睡眠数据 |
| `history_dates` | 可用历史日期 |
| `all` | 全部数据合并 |

`date` 参数 `YYYY-MM-DD` 格式，不传默认查今天。

## Data layout

```
~/.hermes/health_band/
├── data/Gadgetbridge.db        ← 原始数据（从手机同步）
└── derived/
    ├── health_summary.json      ← 今日摘要
    ├── heart_rate_history.json  ← 心率时序
    ├── sleep.json               ← 睡眠
    └── history/                 ← 历史归档
```

## Scripts

> 数据库具体字段请查看 Gadgetbridge 各手环采集字段。不同品牌/型号手环写入的表和字段可能不同。

```bash
# 初始化
python3 scripts/parse_gadgetbridge_summary.py --init

# 手动解析一次
python3 scripts/parse_gadgetbridge_summary.py --once

# 带日期
python3 scripts/parse_gadgetbridge_summary.py --date 2026-06-15

# 指定 profile
python3 scripts/parse_gadgetbridge_summary.py --hermes-home ~/.hermes/profiles/coder
```

## Design notes

- **date 参数优先查 history 归档**，再查 derived。history 丢了就是查不到
- **nap 显示**：`nap_minutes > 0` 时显示 Nap 行。stage 编码 1=light, 2=REM, 3=deep, 4=awake, 5=nap
- **心率源表**：`HUAWEI_ACTIVITY_SAMPLE`，字段 `HEART_RATE`（-1 = 无效）。`HEART_PULSE_SAMPLE` 为空表
- **sleep duration 切分**：按 stages 中 gap>60min 切 block，每个 block 一个 session
- **parse 脚本偶发重复 session**：3 条 score=74/-1/87 的重复行，脚本 bug，非 DB 问题
