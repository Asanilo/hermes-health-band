#!/usr/bin/env python3
import argparse
import json
import time
from pathlib import Path
from datetime import datetime, timezone, timedelta

from parse_gadgetbridge_summary import (
    DEFAULT_TIMEZONE,
    HEALTH_BAND_DIR,
    build_heart_rate_history,
    build_sleep_data,
    build_stress_data,
    build_summary,
    detect_tables,
    project_root,
    resolve_db_path,
    resolve_output_path,
    write_json,
    _prev_date,
    _next_date,
    _safe_iso,
)


def file_state(path):
    stat = path.stat()
    return stat.st_size, stat.st_mtime_ns


def _history_dir(summary_out):
    return summary_out.parent / "history"


def _archive_old(summary_out, history_out, sleep_out, stress_out, old_date):
    """Archive old data for a given date."""
    history_dir = _history_dir(summary_out)
    history_dir.mkdir(parents=True, exist_ok=True)

    import shutil

    old_summary_file = history_dir / f"{old_date}-summary.json"
    if not old_summary_file.exists() and summary_out.exists():
        shutil.copy2(summary_out, old_summary_file)
        print(f"archived: {old_summary_file}", flush=True)

    old_history_file = history_dir / f"{old_date}-heart.json"
    if not old_history_file.exists() and history_out.exists():
        history_out.rename(old_history_file)
        print(f"archived: {old_history_file}", flush=True)

    if sleep_out and sleep_out.exists():
        old_sleep_file = history_dir / f"{old_date}-sleep.json"
        if not old_sleep_file.exists():
            shutil.copy2(sleep_out, old_sleep_file)
            print(f"archived: {old_sleep_file}", flush=True)


def _cleanup_old(history_dir, retention_days):
    """Remove history files older than retention_days."""
    if not history_dir.exists() or retention_days <= 0:
        return
    cutoff = (datetime.now(DEFAULT_TIMEZONE).date() - timedelta(days=retention_days)).isoformat()
    removed = 0
    for f in history_dir.glob("*.json"):
        # Extract date from filename like 2026-06-15-summary.json
        stem = f.stem
        parts = stem.split("-", 3)
        if len(parts) >= 3 and parts[0].isdigit():
            date_str = "-".join(parts[:3])
            if date_str < cutoff:
                f.unlink()
                removed += 1
    if removed:
        print(f"cleaned up {removed} old history files (before {cutoff})", flush=True)


def parse_once(db_path, summary_out, history_out, sleep_out, stress_out, summary_date, last_date, retention_days,
                activity_table="HUAWEI_ACTIVITY_SAMPLE",
                sleep_stats_table="HUAWEI_SLEEP_STATS_SAMPLE",
                sleep_stage_table="HUAWEI_SLEEP_STAGE_SAMPLE",
                stress_table="HUAWEI_STRESS_SAMPLE"):
    """Parse once and return (new_date, did_archive)."""
    summary = build_summary(db_path, summary_date, DEFAULT_TIMEZONE, activity_table=activity_table)
    new_date = summary["summary_date"]

    # Archive if date changed
    did_archive = False
    if last_date and new_date != last_date:
        _archive_old(summary_out, history_out, sleep_out, stress_out, last_date)
        did_archive = True

    # Cleanup old history
    _cleanup_old(_history_dir(summary_out), retention_days)

    # Build sleep - use new_date (resolved from build_summary), not raw summary_date
    sleep_data = build_sleep_data(db_path, new_date, DEFAULT_TIMEZONE,
                                   sleep_stats_table=sleep_stats_table,
                                   sleep_stage_table=sleep_stage_table)
    if sleep_data:
        write_json(sleep_out, sleep_data)

    # Add stress to summary
    stress_data = build_stress_data(db_path, summary_date, DEFAULT_TIMEZONE,
                                     stress_table=stress_table)
    if stress_data:
        summary["stress"] = stress_data["summary"]

    write_json(summary_out, summary)
    history = build_heart_rate_history(db_path, summary_date or new_date, DEFAULT_TIMEZONE,
                                        activity_table=activity_table)
    write_json(history_out, history)
    print(f"parsed {db_path}", flush=True)
    print(f"summary -> {summary_out}", flush=True)
    print(f"history -> {history_out}", flush=True)
    print(f"sleep -> {sleep_out}", flush=True)
    print(f"date={new_date}, archived={did_archive}", flush=True)
    return new_date


def parse_args():
    root = project_root()
    parser = argparse.ArgumentParser(description="Watch Syncthing Gadgetbridge export and refresh JSON outputs.")
    parser.add_argument("--db", help="Path to Gadgetbridge SQLite export. Relative paths are resolved from project root.")
    parser.add_argument("--summary-out", default=str(Path("derived") / "health_summary.json"))
    parser.add_argument("--history-out", default=str(Path("derived") / "heart_rate_history.json"))
    parser.add_argument("--sleep-out", default=str(Path("derived") / "sleep.json"))
    parser.add_argument("--date", help="Summary date in YYYY-MM-DD. Defaults to latest sample date.")
    parser.add_argument("--interval", type=float, default=30.0)
    parser.add_argument("--once", action="store_true", help="Parse once and exit.")
    parser.add_argument("--root", default=str(HEALTH_BAND_DIR), help="Data root directory (default: ~/.hermes/health_band/).")
    parser.add_argument("--hermes-home", default=None, help="Hermes home directory. Overrides --root.")
    parser.add_argument("--retention-days", type=int, default=30, help="Days of history to retain.")
    parser.add_argument("--init", action="store_true",
                        help="Initialize data directory structure and exit.")
    return parser.parse_args()


def main():
    args = parse_args()

    # Resolve root: --hermes-home overrides --root
    if args.hermes_home:
        root = Path(args.hermes_home).expanduser().resolve() / "health_band"
    else:
        root = Path(args.root).expanduser().resolve()

    # --init: delegate to parse script's init logic via import
    if args.init:
        for d in ["data", "derived", "derived/history"]:
            (root / d).mkdir(parents=True, exist_ok=True)
        print(f"✅ Initialized health_band data directory at {root}")
        print(f"   Place Gadgetbridge.db in: {root / 'data' / 'Gadgetbridge.db'}")
        return

    db_path = resolve_db_path(args.db, root)
    summary_out = resolve_output_path(args.summary_out, root)
    history_out = resolve_output_path(args.history_out, root)
    sleep_out = resolve_output_path(args.sleep_out, root)

    # Detect Gadgetbridge tables (multi-brand support)
    tables = detect_tables(db_path)
    act_tbl = tables.get("activity", "HUAWEI_ACTIVITY_SAMPLE")
    slp_stats = tables.get("sleep_stats", "HUAWEI_SLEEP_STATS_SAMPLE")
    slp_stage = tables.get("sleep_stage", "HUAWEI_SLEEP_STAGE_SAMPLE")
    stress_tbl = tables.get("stress", "HUAWEI_STRESS_SAMPLE")
    print(f"   Activity: {act_tbl}")
    if slp_stats: print(f"   Sleep:    {slp_stats}")
    if stress_tbl: print(f"   Stress:   {stress_tbl}")

    # Build common kwargs for parse_once
    _table_kw = dict(
        activity_table=act_tbl, sleep_stats_table=slp_stats,
        sleep_stage_table=slp_stage, stress_table=stress_tbl,
    )

    # Seed last_date from existing summary
    last_date = None
    if summary_out.exists():
        try:
            last_date = json.loads(summary_out.read_text())["summary_date"]
        except (json.JSONDecodeError, KeyError):
            pass

    last_date = parse_once(
        db_path, summary_out, history_out, sleep_out, None,
        args.date, last_date, args.retention_days, **_table_kw
    )
    if args.once:
        return

    # If no explicit --date, only watch for changes; don't overwrite derived files with today's empty data
    if args.date is None:
        last_db_state = file_state(db_path)
        print(f"watching {db_path} (no date set, will not overwrite derived files)", flush=True)
        while True:
            time.sleep(args.interval)
            current_state = file_state(db_path)
            if current_state != last_db_state:
                last_db_state = current_state
                print(f"db changed, re-parsing...", flush=True)
                last_date = parse_once(
                    db_path, summary_out, history_out, sleep_out, None,
                    last_date, last_date, args.retention_days, **_table_kw
                )
            else:
                # Also re-parse on date change (midnight)
                today = datetime.now(DEFAULT_TIMEZONE).date().isoformat()
                if last_date != today:
                    last_date = today
                    parse_once(
                        db_path, summary_out, history_out, sleep_out, None,
                        today, last_date, args.retention_days, **_table_kw
                    )
        return

    last_db_state = file_state(db_path)
    print(f"watching {db_path}", flush=True)
    while True:
        time.sleep(args.interval)
        current_state = file_state(db_path)
        if current_state != last_db_state:
            last_db_state = current_state
            last_date = parse_once(
                db_path, summary_out, history_out, sleep_out, None,
                args.date, last_date, args.retention_days, **_table_kw
            )


if __name__ == "__main__":
    main()
