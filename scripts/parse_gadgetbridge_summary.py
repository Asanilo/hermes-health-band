#!/usr/bin/env python3
import argparse
import json
import sqlite3
from datetime import datetime, timezone, timedelta
from pathlib import Path


DEFAULT_TIMEZONE = timezone(timedelta(hours=8))
DEFAULT_HERMES_HOME = Path.home() / ".hermes"
HEALTH_BAND_DIR = DEFAULT_HERMES_HOME / "health_band"


def project_root():
    return Path(__file__).resolve().parents[1]


def default_db_candidates(root):
    return [
        root / "data" / "Gadgetbridge.db",
        root / "data" / "Gadgetbridge.sqlite",
        root / "data" / "Gadgetbridge",
        # Legacy paths
        root / "data" / "gadgetbridge" / "Gadgetbridge.db",
        root / "synced" / "gadgetbridge" / "Gadgetbridge.db",
    ]


def resolve_db_path(db_arg, root):
    if db_arg:
        path = Path(db_arg).expanduser()
        if not path.is_absolute():
            path = root / path
        if not path.exists():
            raise FileNotFoundError(f"database not found: {path}")
        return path

    for path in default_db_candidates(root):
        if path.exists():
            return path

    searched = "\n".join(str(path) for path in default_db_candidates(root))
    raise FileNotFoundError(f"database not found. Searched:\n{searched}")


def day_bounds(summary_date, tz):
    start = datetime.fromisoformat(summary_date).replace(tzinfo=tz)
    return int(start.timestamp() * 1000), int((start.timestamp() + 86400) * 1000)


def day_bounds_s(summary_date, tz):
    """Seconds-level day bounds for tables that store seconds (ACTIVITY)."""
    start = datetime.fromisoformat(summary_date).replace(tzinfo=tz)
    return int(start.timestamp()), int((start.timestamp() + 86400))


def _safe_iso(ts, tz, is_ms=False):
    """Convert timestamp to ISO string, returning None for invalid values.
    
    Args:
        ts: raw timestamp value from DB
        tz: timezone to attach
        is_ms: True if ts is milliseconds (HUAWEI_STRESS_SAMPLE, HUAWEI_SLEEP_STATS_SAMPLE,
               HUAWEI_SLEEP_STAGE_SAMPLE), False if seconds (HUAWEI_ACTIVITY_SAMPLE)
    """
    if ts is None or ts <= 0:
        return None
    try:
        if is_ms:
            ts = ts / 1000.0
        return datetime.fromtimestamp(ts, tz).isoformat(timespec="seconds")
    except (ValueError, OSError):
        return None


def latest_sample_date(connection, tz):
    row = connection.execute("select max(TIMESTAMP) from HUAWEI_ACTIVITY_SAMPLE").fetchone()
    if not row or row[0] is None:
        return datetime.now(tz).date().isoformat()
    return datetime.fromtimestamp(row[0], tz).date().isoformat()


def first_row(connection, query, params=()):
    return connection.execute(query, params).fetchone()


def build_summary(db_path, summary_date=None, tz=DEFAULT_TIMEZONE):
    with sqlite3.connect(db_path) as connection:
        # Default to TODAY's date, not latest sample date
        if summary_date is None:
            summary_date = datetime.now(tz).date().isoformat()

        start, end = day_bounds(summary_date, tz)
        start_s, end_s = day_bounds_s(summary_date, tz)
        device = first_row(
            connection,
            "select NAME, MANUFACTURER, IDENTIFIER, MODEL from DEVICE order by _id limit 1",
        )
        latest_ts = first_row(connection, "select max(TIMESTAMP) from HUAWEI_ACTIVITY_SAMPLE")[0]
        row = first_row(
            connection,
            """
            select
              sum(case when STEPS > 0 then STEPS else 0 end),
              sum(case when DISTANCE > 0 then DISTANCE else 0 end),
              sum(case when CALORIES > 0 then CALORIES else 0 end),
              count(case when HEART_RATE > 0 then 1 end),
              min(case when HEART_RATE > 0 then HEART_RATE end),
              max(case when HEART_RATE > 0 then HEART_RATE end),
              avg(case when HEART_RATE > 0 then HEART_RATE end),
              count(case when SPO > 0 then 1 end),
              avg(case when SPO > 0 then SPO end)
            from HUAWEI_ACTIVITY_SAMPLE
            where TIMESTAMP >= ? and TIMESTAMP < ?
            """,
            (start_s, end_s),
        )
        battery = first_row(
            connection,
            "select LEVEL, TIMESTAMP from BATTERY_LEVEL order by TIMESTAMP desc limit 1",
        )

    steps, distance, calories_raw, hr_count, hr_min, hr_max, hr_avg, spo_count, spo_avg = row
    now = datetime.now(tz).isoformat(timespec="seconds")

    return {
        "timestamp": now,
        "summary_date": summary_date,
        "data_latest_at": _safe_iso(latest_ts, tz) if latest_ts else None,
        "source": "gadgetbridge_export",
        "device": {
            "name": device[0] if device else None,
            "manufacturer": device[1] if device else None,
            "identifier": device[2] if device else None,
            "model": device[3] if device else None,
        },
        "steps_today": steps or 0,
        "distance_meters_today": distance or 0,
        "active_calories_raw_today": calories_raw or 0,
        "active_calories_kcal_estimate": round((calories_raw or 0) / 1000, 1),
        "heart_rate_samples": hr_count or 0,
        "heart_rate_min": hr_min,
        "heart_rate_max": hr_max,
        "heart_rate_avg": round(hr_avg, 1) if hr_avg is not None else None,
        "spo2_samples": spo_count or 0,
        "spo2_avg": round(spo_avg, 1) if spo_avg is not None else None,
        "battery_percent": battery[0] if battery else None,
        "battery_updated_at": _safe_iso(battery[1], tz) if battery else None,
        "fresh": True,
        "notes": "Calories appear to be stored in Gadgetbridge raw units; kcal estimate divides raw value by 1000.",
    }


def build_heart_rate_history(db_path, summary_date=None, tz=DEFAULT_TIMEZONE):
    with sqlite3.connect(db_path) as connection:
        if summary_date is None:
            summary_date = datetime.now(tz).date().isoformat()
        start_s, end_s = day_bounds_s(summary_date, tz)
        rows = connection.execute(
            """
            select TIMESTAMP, HEART_RATE
            from HUAWEI_ACTIVITY_SAMPLE
            where TIMESTAMP >= ? and TIMESTAMP < ? and HEART_RATE > 0
            order by TIMESTAMP
            """,
            (start_s, end_s),
        ).fetchall()

    return {
        "timestamp": datetime.now(tz).isoformat(timespec="seconds"),
        "summary_date": summary_date,
        "source": "gadgetbridge_export",
        "samples": [
            {
                "timestamp": _safe_iso(timestamp, tz),
                "heart_rate": heart_rate,
            }
            for timestamp, heart_rate in rows
        ],
    }


def build_sleep_data(db_path, summary_date=None, tz=DEFAULT_TIMEZONE):
    """Build sleep data for a given date (or latest available night)."""
    with sqlite3.connect(db_path) as connection:
        if summary_date is None:
            # Get the latest sleep session date
            row = connection.execute(
                "select max(WAKEUP_TIME) from HUAWEI_SLEEP_STATS_SAMPLE"
            ).fetchone()
            if row and row[0]:
                # Find which date this belongs to (wakeup time in local TZ)
                wakeup_dt = datetime.fromtimestamp(row[0] / 1000, tz=tz)
                # Sleep sessions span midnight, so use wakeup date
                summary_date = wakeup_dt.date().isoformat()
            else:
                return None

        # Build raw sleep stages for this date's sleep session
        # Find sessions that overlap with this date
        # Each session: BED_TIME → next day's WAKEUP_TIME
        # Build raw sleep stages for this date's sleep session
        # Find sessions that overlap with this date
        # Each session: BED_TIME → next day's WAKEUP_TIME
        sessions = []
        # WAKEUP_TIME is ms; SQL localtime does UTC+8 conversion
        # We mirror that in Python to avoid double-conversion
        prev = datetime.fromisoformat(_prev_date(summary_date)).replace(tzinfo=tz)
        curr = datetime.fromisoformat(summary_date).replace(tzinfo=tz)
        next_d = datetime.fromisoformat(_next_date(summary_date)).replace(tzinfo=tz)
        prev_ms = int(prev.timestamp() * 1000)
        curr_ms = int(curr.timestamp() * 1000)
        next_ms = int(next_d.timestamp() * 1000)

        rows = connection.execute(
            """
            select TIMESTAMP, DEVICE_ID, USER_ID, SLEEP_SCORE, BED_TIME, WAKEUP_TIME,
                   DEEP_PART, WAKE_COUNT, SLEEP_DATA_QUALITY,
                   MIN_HEART_RATE, AVG_HEART_RATE,
                   MIN_OXYGEN_SATURATION, AVG_OXYGEN_SATURATION
            from HUAWEI_SLEEP_STATS_SAMPLE
            where WAKEUP_TIME >= ? and WAKEUP_TIME < ?
            order by WAKEUP_TIME
            """,
            (prev_ms, next_ms),
        ).fetchall()

        # Column order MUST match the SELECT above:
        #   0:TIMESTAMP 1:DEVICE_ID 2:USER_ID 3:SLEEP_SCORE 4:BED_TIME 5:WAKEUP_TIME
        #   6:DEEP_PART 7:WAKE_COUNT 8:SLEEP_DATA_QUALITY 9:MIN_HEART_RATE
        #   10:AVG_HEART_RATE 11:MIN_OXYGEN_SATURATION 12:AVG_OXYGEN_SATURATION
        for row in rows:
            ts, dev_id, user_id, score, bed_ts, wake_ts, deep, wake_count, quality, min_hr, avg_hr, min_spo2, avg_spo2 = row
            bed_iso = _safe_iso(bed_ts, tz, is_ms=True) if bed_ts and bed_ts > 0 else None
            wake_iso = _safe_iso(wake_ts, tz, is_ms=True) if wake_ts and wake_ts > 0 else None
            summary_date_date = datetime.fromisoformat(summary_date).date()
            valid = False
            # Assign session to the date its BED_TIME falls on (not wakeup date)
            if bed_iso:
                try:
                    bed_dt = datetime.fromisoformat(bed_iso.replace("+08:00", ""))
                    if bed_dt.date() == summary_date_date:
                        valid = True
                except Exception:
                    pass
            # Fallback: if no valid bed_time, use wakeup date
            if not valid and wake_iso:
                try:
                    wake_dt = datetime.fromisoformat(wake_iso.replace("+08:00", ""))
                    if wake_dt.date() == summary_date_date:
                        valid = True
                except Exception:
                    pass
            if not valid:
                continue
            sessions.append({
                "sleep_score": score,
                "bed_time": _safe_iso(bed_ts, tz, is_ms=True) if bed_ts and bed_ts > 0 else None,
                "wakeup_time": _safe_iso(wake_ts, tz, is_ms=True) if wake_ts and wake_ts > 0 else None,
                "deep_minutes": deep if deep and deep > 0 else 0,
                "wake_count": wake_count if wake_count and wake_count >= 0 else 0,
            })

        # Also get raw sleep stage data for detailed view
        # Get stages from two days: the sleep session that ends on this date
        # is the one where wakeup_time falls on this date
        # STAGE_SAMPLE.TIMESTAMP is ms; filter entirely in Python to avoid SQL localtime double-conversion
        all_stages = connection.execute(
            "select TIMESTAMP, STAGE from HUAWEI_SLEEP_STAGE_SAMPLE order by TIMESTAMP"
        ).fetchall()
        stage_rows = [
            (ts, stage) for ts, stage in all_stages
            if prev_ms <= ts < next_ms
        ]

        # Split stages into blocks separated by gaps > 60min
        # (each block = one sleep session: bedtime -> wakeup)
        def split_stage_blocks(rows, gap_thresh_ms=60 * 60 * 1000):
            if not rows:
                return []
            blocks = []
            block_start = rows[0][0]
            prev_ts = rows[0][0]
            for ts, stage in rows[1:]:
                if ts - prev_ts > gap_thresh_ms:
                    blocks.append((block_start, prev_ts))
                    block_start = ts
                prev_ts = ts
            blocks.append((block_start, prev_ts))
            return blocks

        stage_blocks = split_stage_blocks(stage_rows)

        # Stage encoding (Gadgetbridge):
        # stage 1=light, stage 2=REM, stage 3=deep, stage 4=awake, stage 5=nap
        STAGE_NAMES = {1: "light", 2: "rem", 3: "deep", 4: "awake", 5: "nap"}

        def build_session_from_block(block_start_ms, block_end_ms, stage_rows, tz):
            """Compute stage counts and inferred bedtime for a stage block."""
            block_stages = [(ts, s) for ts, s in stage_rows if block_start_ms <= ts <= block_end_ms]
            stage_counts = {1: 0, 2: 0, 3: 0, 4: 0, 5: 0}
            for _, stg in block_stages:
                stage_counts[stg] = stage_counts.get(stg, 0) + 1
            awake_min = stage_counts.get(4, 0)
            rem_min = stage_counts.get(2, 0)
            light_min = stage_counts.get(1, 0)
            deep_min = stage_counts.get(3, 0)
            nap_min = stage_counts.get(5, 0)
            total_min = awake_min + rem_min + light_min + deep_min + nap_min
            # Inferred bedtime: first non-awake stage
            inferred_bed = None
            for ts, stg in block_stages:
                if stg != 4:
                    inferred_bed = _safe_iso(ts, tz, is_ms=True)
                    break
            if inferred_bed is None and block_stages:
                inferred_bed = _safe_iso(block_stages[0][0], tz, is_ms=True)
            return {
                "total_min": total_min,
                "stage_counts": stage_counts,
                "inferred_bed": inferred_bed,
                "awake_min": awake_min,
                "rem_min": rem_min,
                "light_min": light_min,
                "deep_min": deep_min,
                "nap_min": nap_min,
            }

        # Filter to only valid sessions (score >= 0)
        valid_sessions = [
            {
                "sleep_score": s["sleep_score"],
                "bed_time": s["bed_time"],
                "wakeup_time": s["wakeup_time"],
                "wake_count": s["wake_count"],
            }
            for s in sessions
            if s["sleep_score"] is not None and s["sleep_score"] >= 0
        ]

        computed_sessions = []
        for session in valid_sessions:
            wake_str = session.get("wakeup_time")
            wake_dt = None
            if wake_str:
                try:
                    wake_dt = datetime.fromisoformat(wake_str.replace("+08:00", ""))
                except Exception:
                    pass
            # Find stage block whose end time is closest to this wakeup
            best_block = None
            if wake_dt and stage_blocks:
                wake_ms = int(wake_dt.timestamp() * 1000)
                best_diff = float("inf")
                for b_start, b_end in stage_blocks:
                    diff = abs(b_end - wake_ms)
                    if diff < best_diff:
                        best_diff = diff
                        best_block = (b_start, b_end)
            # Fall back to all stages if no valid wakeup match
            if best_block is None and stage_blocks:
                best_block = stage_blocks[-1]
            if best_block:
                block_data = build_session_from_block(
                    best_block[0], best_block[1], stage_rows, tz
                )
                total_min = block_data["total_min"]
                stage_counts = block_data["stage_counts"]
                awake_min = block_data["awake_min"]
                rem_min = block_data["rem_min"]
                light_min = block_data["light_min"]
                deep_min = block_data["deep_min"]
                nap_min = block_data["nap_min"]
                inferred_bed = block_data["inferred_bed"]
            else:
                total_min = 0
                stage_counts = {1: 0, 2: 0, 3: 0, 4: 0, 5: 0}
                awake_min = rem_min = light_min = deep_min = nap_min = 0
                inferred_bed = None
            # Use DB bed_time if valid, otherwise fall back to inferred
            bed_time = session.get("bed_time")
            if not bed_time and inferred_bed:
                bed_time = inferred_bed
            computed_sessions.append({
                "sleep_score": session.get("sleep_score"),
                "bed_time": bed_time,
                "wakeup_time": session.get("wakeup_time"),
                "duration_minutes": total_min,
                "deep_minutes": deep_min,
                "light_minutes": light_min,
                "rem_minutes": rem_min,
                "awake_minutes": awake_min,
                "nap_minutes": nap_min,
                "wake_count": session.get("wake_count", 0),
                "stage_counts": stage_counts,
            })

        # Stages output: all stages for this date range
        stages = [
            {"timestamp": _safe_iso(ts, tz, is_ms=True), "stage": stage}
            for ts, stage in stage_rows
        ]

    return {
        "timestamp": datetime.now(tz).isoformat(timespec="seconds"),
        "summary_date": summary_date,
        "source": "gadgetbridge_export",
        "sessions": computed_sessions,
        "stages": stages,
    }


def build_stress_data(db_path, summary_date=None, tz=DEFAULT_TIMEZONE):
    """Build stress data for a given date."""
    with sqlite3.connect(db_path) as connection:
        if summary_date is None:
            summary_date = latest_sample_date(connection, tz)
        start, end = day_bounds(summary_date, tz)
        rows = connection.execute(
            """
            select TIMESTAMP, STRESS, LEVEL
            from HUAWEI_STRESS_SAMPLE
            where TIMESTAMP >= ? and TIMESTAMP < ?
            order by TIMESTAMP
            """,
            (start, end),  # day_bounds returns ms for stress table
        ).fetchall()

    # Level mapping: 1=relaxed, 2=medium, 3=high
    level_label = {1: "relaxed", 2: "medium", 3: "high"}
    label_to_int = {"relaxed": 1, "medium": 2, "high": 3}
    samples = [
        {
            "timestamp": _safe_iso(ts, tz, is_ms=True),
            "stress_value": stress,
            "level": level_label.get(level, f"unknown({level})"),
        }
        for ts, stress, level in rows
    ]

    # Compute summary stats
    if samples:
        values = [s["stress_value"] for s in samples]
        counts = {1: 0, 2: 0, 3: 0}
        for s in samples:
            l = label_to_int.get(s["level"], 3)
            counts[l] = counts.get(l, 0) + 1
        summary = {
            "count": len(values),
            "min": min(values),
            "max": max(values),
            "avg": round(sum(values) / len(values), 1),
            "relaxed_min": counts.get(1, 0),
            "medium_min": counts.get(2, 0),
            "high_min": counts.get(3, 0),
        }
    else:
        summary = {"count": 0, "min": None, "max": None, "avg": None,
                   "relaxed_min": 0, "medium_min": 0, "high_min": 0}

    return {
        "timestamp": datetime.now(tz).isoformat(timespec="seconds"),
        "summary_date": summary_date,
        "source": "gadgetbridge_export",
        "summary": summary,
        "samples": samples,
    }


def _next_date(date_str):
    d = datetime.fromisoformat(date_str).date()
    return (d + timedelta(days=1)).isoformat()


def _prev_date(date_str):
    d = datetime.fromisoformat(date_str).date()
    return (d - timedelta(days=1)).isoformat()


def write_json(path, payload):
    path.parent.mkdir(parents=True, exist_ok=True)
    temp_path = path.with_name(path.name + ".tmp")
    temp_path.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    temp_path.replace(path)


def parse_args():
    root = project_root()
    parser = argparse.ArgumentParser(description="Parse Gadgetbridge SQLite export into JSON files.")
    parser.add_argument("--db", help="Path to Gadgetbridge SQLite export. Relative paths are resolved from project root.")
    parser.add_argument("--date", help="Summary date in YYYY-MM-DD. Defaults to the latest sample date.")
    parser.add_argument("--summary-out", default=str(Path("derived") / "health_summary.json"))
    parser.add_argument("--history-out", default=str(Path("derived") / "heart_rate_history.json"))
    parser.add_argument("--sleep-out", default=str(Path("derived") / "sleep.json"))
    parser.add_argument("--stress-out", default=str(Path("derived") / "stress.json"))
    parser.add_argument("--no-history", action="store_true")
    parser.add_argument("--root", default=str(HEALTH_BAND_DIR), help="Data root directory (default: ~/.hermes/health_band/).")
    parser.add_argument("--hermes-home", default=None, help="Hermes home directory. Overrides --root to <hermes-home>/health_band/.")
    parser.add_argument("--skip-if-unchanged", action="store_true",
                        help="Skip parsing if database file hasn't changed (for cron jobs)")
    parser.add_argument("--init", action="store_true",
                        help="Initialize data directory structure and exit.")
    return parser.parse_args()


def resolve_output_path(value, root):
    path = Path(value).expanduser()
    if not path.is_absolute():
        path = root / path
    return path


def file_state(path):
    """Return (size, mtime_ns) for change detection."""
    try:
        stat = path.stat()
        return stat.st_size, stat.st_mtime_ns
    except FileNotFoundError:
        return None, None


def archive_if_date_changed(summary_out, history_out, sleep_out, stress_out, new_date):
    """Archive old data if the date has changed."""
    history_dir = summary_out.parent / "history"
    history_dir.mkdir(parents=True, exist_ok=True)

    # Check existing summary for date
    if summary_out.exists():
        try:
            old_summary = json.loads(summary_out.read_text(encoding="utf-8"))
            old_date = old_summary.get("summary_date")
            if old_date and old_date != new_date:
                # Archive old summary
                old_summary_file = history_dir / f"{old_date}-summary.json"
                if not old_summary_file.exists():
                    import shutil
                    shutil.copy2(summary_out, old_summary_file)
                    print(f"archived: {old_summary_file}")

                # Archive old history
                old_history_file = history_dir / f"{old_date}.json"
                if history_out.exists() and not old_history_file.exists():
                    history_out.rename(old_history_file)
                    print(f"archived: {old_history_file}")

                # Archive old sleep if exists
                if sleep_out and sleep_out.exists():
                    old_sleep_file = history_dir / f"{old_date}-sleep.json"
                    if not old_sleep_file.exists():
                        import shutil
                        shutil.copy2(sleep_out, old_sleep_file)
                        print(f"archived: {old_sleep_file}")

                # Archive old stress if exists
                if stress_out and stress_out.exists():
                    old_stress_file = history_dir / f"{old_date}-stress.json"
                    if not old_stress_file.exists():
                        import shutil
                        shutil.copy2(stress_out, old_stress_file)
                        print(f"archived: {old_stress_file}")
        except (json.JSONDecodeError, KeyError):
            pass


def main():
    args = parse_args()

    # Resolve root: --hermes-home overrides --root
    if args.hermes_home:
        root = Path(args.hermes_home).expanduser().resolve() / "health_band"
    else:
        root = Path(args.root).expanduser().resolve()

    # --init: create directory structure and exit
    if args.init:
        for d in ["data", "derived", "derived/history"]:
            (root / d).mkdir(parents=True, exist_ok=True)
        readme = root / "data" / "README.txt"
        if not readme.exists():
            readme.write_text(
                "Place your Gadgetbridge SQLite export file here.\n"
                "Expected filename: Gadgetbridge.db\n"
                "Sync method: Syncthing or manual copy from phone.\n",
                encoding="utf-8",
            )
        print(f"✅ Initialized health_band data directory at {root}")
        print(f"   Place Gadgetbridge.db in: {root / 'data' / 'Gadgetbridge.db'}")
        print(f"   Then run: python3 scripts/parse_gadgetbridge_summary.py --once")
        return

    db_path = resolve_db_path(args.db, root)
    summary_out = resolve_output_path(args.summary_out, root)
    history_out = resolve_output_path(args.history_out, root)
    sleep_out = resolve_output_path(args.sleep_out, root)
    stress_out = resolve_output_path(args.stress_out, root)

    # Skip if database unchanged (for cron jobs)
    if args.skip_if_unchanged:
        state_file = root / "derived" / ".db_state"
        current_state = file_state(db_path)

        if state_file.exists():
            try:
                saved_state = tuple(state_file.read_text().strip().split(","))
                saved_state = (int(saved_state[0]), int(saved_state[1]))
                if current_state == saved_state:
                    # Database unchanged, skip parsing
                    return
            except (ValueError, IndexError):
                pass

        # Save current state for next check
        state_file.parent.mkdir(parents=True, exist_ok=True)
        state_file.write_text(f"{current_state[0]},{current_state[1]}")

    summary = build_summary(db_path, args.date, DEFAULT_TIMEZONE)
    new_date = summary["summary_date"]

    # Archive old data if date changed
    archive_if_date_changed(summary_out, history_out, sleep_out, stress_out, new_date)

    write_json(summary_out, summary)
    print(f"summary: {summary_out}")

    if not args.no_history:
        history = build_heart_rate_history(db_path, args.date or new_date, DEFAULT_TIMEZONE)
        write_json(history_out, history)
        print(f"history: {history_out}")

    # Write sleep data
    sleep_data = build_sleep_data(db_path, args.date, DEFAULT_TIMEZONE)
    if sleep_data:
        write_json(sleep_out, sleep_data)
        print(f"sleep: {sleep_out}")

    # Add stress to summary (in-place, re-read from disk)
    summary = json.loads(summary_out.read_text(encoding="utf-8"))
    stress_data = build_stress_data(db_path, args.date, DEFAULT_TIMEZONE)
    if stress_data:
        summary["stress"] = stress_data["summary"]
    write_json(summary_out, summary)
    print(f"summary (with stress): {summary_out}")


if __name__ == "__main__":
    main()
