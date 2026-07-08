"""Health Band tools for Hermes.

Provides tools to read health data from HUAWEI Band 8 via Gadgetbridge sync.
Data lives in ~/.hermes/health_band/
"""
from __future__ import annotations

import json
import os
from datetime import datetime, timezone, timedelta
from pathlib import Path
from typing import Any, Dict, List, Optional

TZ = timezone(timedelta(hours=8))

# Data directory: always ~/.hermes/health_band/ (shared across all profiles)
HERMES_HOME = Path.home() / ".hermes"
HEALTH_BAND_DIR = HERMES_HOME / "health_band"
DERIVED_DIR = HEALTH_BAND_DIR / "derived"
HISTORY_DIR = DERIVED_DIR / "history"
DATA_DIR = HEALTH_BAND_DIR / "data"


def _freshness_emoji(iso_timestamp: Optional[str]) -> str:
    """Return freshness indicator based on timestamp age."""
    if not iso_timestamp:
        return "⚫"
    try:
        ts = datetime.fromisoformat(iso_timestamp)
        if ts.tzinfo is None:
            ts = ts.replace(tzinfo=TZ)
        age = datetime.now(TZ) - ts
        minutes = age.total_seconds() / 60
        if minutes < 30:
            return "🟢"
        elif minutes < 120:
            return "🟡"
        else:
            return "🔴"
    except (ValueError, TypeError):
        return "⚫"


def _format_age(iso_timestamp: Optional[str]) -> str:
    """Return human-readable age string."""
    if not iso_timestamp:
        return "no data"
    try:
        ts = datetime.fromisoformat(iso_timestamp)
        if ts.tzinfo is None:
            ts = ts.replace(tzinfo=TZ)
        age = datetime.now(TZ) - ts
        minutes = int(age.total_seconds() / 60)
        if minutes < 1:
            return "just now"
        elif minutes < 60:
            return f"{minutes} min ago"
        elif minutes < 1440:
            hours = minutes // 60
            return f"{hours} hr ago"
        else:
            days = minutes // 1440
            return f"{days} day ago"
    except (ValueError, TypeError):
        return "unknown"


def _load_json(path: Path) -> Optional[Dict]:
    """Load JSON file, return None if missing."""
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (FileNotFoundError, json.JSONDecodeError):
        return None


def _format_summary(data: Dict) -> str:
    """Format health summary for agent output."""
    if not data:
        return "No health summary available. Gadgetbridge data may not be synced yet."

    fresh = _freshness_emoji(data.get("timestamp"))
    age = _format_age(data.get("timestamp"))
    device = data.get("device", {}).get("name", "Unknown")

    lines = [
        f"{fresh} Health Summary ({age})",
        f"Device: {device}",
        f"Date: {data.get('summary_date', 'Unknown')}",
        "",
        f"Steps: {data.get('steps_today', 0):,}",
        f"Distance: {data.get('distance_meters_today', 0):,} m",
        f"Calories: {data.get('active_calories_kcal_estimate', 0)} kcal",
        "",
        f"Heart Rate: {data.get('heart_rate_min', '?')}-{data.get('heart_rate_max', '?')} "
        f"(avg {data.get('heart_rate_avg', '?')}) BPM",
        f"HR Samples: {data.get('heart_rate_samples', 0)}",
        "",
        f"SpO2: {data.get('spo2_avg', '?')}% ({data.get('spo2_samples', 0)} samples)",
        f"Battery: {data.get('battery_percent', '?')}%",
        "",
        f"Stress: avg {data.get('stress', {}).get('avg', '?')} "
        f"(relaxed {data.get('stress', {}).get('relaxed_min', 0)} min / "
        f"medium {data.get('stress', {}).get('medium_min', 0)} min / "
        f"high {data.get('stress', {}).get('high_min', 0)} min)",
    ]
    return "\n".join(lines)


def _format_history(data: Dict) -> str:
    """Format heart rate history for agent output."""
    if not data:
        return "No heart rate history available."

    fresh = _freshness_emoji(data.get("timestamp"))
    age = _format_age(data.get("timestamp"))
    samples = data.get("samples", [])

    # Basic stats
    rates = [s["heart_rate"] for s in samples] if samples else []

    # Recent trend (last 10 samples)
    recent = samples[-10:] if len(samples) >= 10 else samples
    recent_rates = [s["heart_rate"] for s in recent] if recent else []

    # Time range
    first_ts = samples[0].get("timestamp", "?") if samples else "?"
    last_ts = samples[-1].get("timestamp", "?") if samples else "?"

    lines = [
        f"{fresh} Heart Rate History ({age})",
        f"Date: {data.get('summary_date', 'Unknown')}",
        f"Time range: {first_ts} → {last_ts}",
        f"Total samples: {len(samples)}",
    ]

    if rates:
        lines.extend([
            "",
            f"Min: {min(rates)} BPM",
            f"Max: {max(rates)} BPM",
            f"Avg: {sum(rates)/len(rates):.1f} BPM",
        ])
        if recent_rates:
            lines.append("")
            lines.append(f"Recent trend (last {len(recent)} samples): {sum(recent_rates)/len(recent_rates):.1f} BPM")

    # Show last 15 samples
    if samples:
        last_n = samples[-15:] if len(samples) >= 15 else samples
        lines.append("")
        lines.append(f"Latest {len(last_n)} readings:")
        for s in last_n:
            lines.append(f"  {s['timestamp']}: {s['heart_rate']} BPM")

    return "\n".join(lines)


def _format_sleep(data: Optional[Dict]) -> str:
    """Format sleep data for agent output."""
    if not data:
        return "No sleep data available yet. Data appears after first sleep cycle."

    sessions = data.get("sessions", [])
    if not sessions:
        return "No sleep sessions recorded."

    lines = ["🌙 Sleep Data"]
    for session in sessions:
        score = session.get("sleep_score")
        bed_ts = session.get("bed_time")
        wake_ts = session.get("wakeup_time")
        bed = (bed_ts.replace("+08:00", "") if bed_ts else "?")
        wake = (wake_ts.replace("+08:00", "") if wake_ts else "?")
        duration_min = session.get("duration_minutes", 0)
        deep_min = session.get("deep_minutes", 0)
        light_min = session.get("light_minutes", 0)
        rem_min = session.get("rem_minutes", 0)
        awake_min = session.get("awake_minutes", 0)
        nap_min = session.get("nap_minutes", 0)
        wake_count = session.get("wake_count", 0)

        # Build readable time range
        if bed == "?" and wake == "?":
            time_range = "time unknown"
        elif bed == "?":
            time_range = f"→ {wake}"
        elif wake == "?":
            time_range = f"{bed} → ?"
        else:
            time_range = f"{bed} → {wake}"

        lines.extend([
            "",
            f"Score: {score if score and score > 0 else '?'}",
            f"Time: {time_range}",
            f"Duration: {duration_min} min ({duration_min/60:.1f} hr)",
            f"Deep: {deep_min} min",
            f"Light: {light_min} min",
            f"REM: {rem_min} min",
            f"Nap: {nap_min} min",
            f"Awake: {awake_min} min ({wake_count} wake-ups)",
        ])

    return "\n".join(lines)


def _list_history_dates() -> List[str]:
    """List available history dates."""
    if not HISTORY_DIR.exists():
        return []
    dates = set()
    for f in HISTORY_DIR.glob("*.json"):
        # Extract date from filenames like: 2026-06-15.json, 2026-06-15-summary.json, 2026-06-15-sleep.json
        stem = f.stem  # e.g. "2026-06-15" or "2026-06-15-summary"
        parts = stem.split("-", 3)
        if len(parts) >= 3:
            # Take YYYY-MM-DD part
            date_str = "-".join(parts[:3])
            dates.add(date_str)
    return sorted(dates)


def _format_all(date: Optional[str] = None) -> str:
    """Combine all available data for a given date."""
    sections = []

    today = datetime.now(TZ).strftime("%Y-%m-%d")
    target_date = date or today

    # Load summary
    if date:
        summary_file = HISTORY_DIR / f"{date}-summary.json"
        if summary_file.exists():
            summary = _load_json(summary_file)
        elif date == today:
            summary = _load_json(DERIVED_DIR / "health_summary.json")
        else:
            summary = None
    else:
        summary = _load_json(DERIVED_DIR / "health_summary.json")
    if summary:
        sections.append(_format_summary(summary))

    # Load heart rate history
    if date:
        history_file = HISTORY_DIR / f"{date}-heart.json"
        if history_file.exists():
            history = _load_json(history_file)
        elif date == today:
            history = _load_json(DERIVED_DIR / "heart_rate_history.json")
        else:
            history = {"samples": []}
    else:
        history = _load_json(DERIVED_DIR / "heart_rate_history.json")
    if history:
        sections.append("")
        sections.append("---")
        sections.append("")
        sections.append(_format_history(history))

    # Load sleep data
    if date:
        sleep_file = HISTORY_DIR / f"{date}-sleep.json"
        if sleep_file.exists():
            sleep_data = _load_json(sleep_file)
        elif date == today:
            sleep_data = _load_json(DERIVED_DIR / "sleep.json")
        else:
            sleep_data = None
    else:
        sleep_data = _load_json(DERIVED_DIR / "sleep.json")
    if sleep_data:
        sections.append("")
        sections.append("---")
        sections.append("")
        sections.append(_format_sleep(sleep_data))

    if not sections:
        return "No health data available. Check Gadgetbridge sync status."

    return "\n".join(sections)


# Tool schema
HEALTH_BAND_SCHEMA = {
    "type": "function",
    "function": {
        "name": "health_band",
        "description": (
            "Read health data from HUAWEI Band 8 (heart rate, steps, SpO2, sleep) "
            "via Gadgetbridge sync. Use when user asks about heart rate, health, "
            "exercise, sleep, or band status."
        ),
        "parameters": {
            "type": "object",
            "properties": {
                "action": {
                    "type": "string",
                    "enum": ["summary", "hear_my_heart", "sleep", "history_dates", "all"],
                    "description": (
                        "What data to read:\n"
                        "- summary: Today's health summary (steps, HR stats, SpO2, battery)\n"
                        "- hear_my_heart: Heart rate time series (default, use 'date' param for historical)\n"
                        "- sleep: Sleep data (when available)\n"
                        "- history_dates: List available historical dates\n"
                        "- all: All available data combined"
                    ),
                    "default": "hear_my_heart",
                },
                "date": {
                    "type": "string",
                    "description": "Date in YYYY-MM-DD format for summary/hear_my_heart/sleep/all actions. Defaults to today.",
                },
            },
            "required": [],
        },
    },
}


def _check_health_band_available() -> bool:
    """Check if health band data directory exists."""
    return HEALTH_BAND_DIR.exists()


def _handle_health_band(args: Dict[str, Any], **kwargs) -> str:
    """Handle health_band tool calls."""
    action = args.get("action", "hear_my_heart")
    date = args.get("date")

    if action == "summary":
        if date:
            # Try history directory first, then derived root
            summary_file = HISTORY_DIR / f"{date}-summary.json"
            if summary_file.exists():
                data = _load_json(summary_file)
            else:
                today = datetime.now(TZ).strftime("%Y-%m-%d")
                if date == today:
                    data = _load_json(DERIVED_DIR / "health_summary.json")
                else:
                    return f"No summary data for {date}."
        else:
            data = _load_json(DERIVED_DIR / "health_summary.json")
        return _format_summary(data)
    elif action == "hear_my_heart":
        if date:
            # Try history directory first, then derived root
            history_file = HISTORY_DIR / f"{date}.json"
            if history_file.exists():
                data = _load_json(history_file)
            else:
                # Check if it's today's date - use root derived
                today = datetime.now(TZ).strftime("%Y-%m-%d")
                if date == today:
                    data = _load_json(DERIVED_DIR / "heart_rate_history.json")
                else:
                    available = _list_history_dates()
                    if available:
                        return f"No data for {date}. Available dates: {', '.join(available)}"
                    else:
                        return f"No data for {date}. No historical data available yet."
        else:
            data = _load_json(DERIVED_DIR / "heart_rate_history.json")
        return _format_history(data)
    elif action == "history_dates":
        dates = _list_history_dates()
        # Also check today's data
        today_data = DERIVED_DIR / "heart_rate_history.json"
        if today_data.exists():
            today_str = datetime.now(TZ).strftime("%Y-%m-%d")
            if today_str not in dates:
                dates.append(today_str)
        if not dates:
            return "No historical data available yet."
        return "Available dates:\n" + "\n".join(f"  {d}" for d in sorted(dates))
    elif action == "sleep":
        if date:
            sleep_file = HISTORY_DIR / f"{date}-sleep.json"
            if sleep_file.exists():
                data = _load_json(sleep_file)
            else:
                today = datetime.now(TZ).strftime("%Y-%m-%d")
                if date == today:
                    data = _load_json(DERIVED_DIR / "sleep.json")
                else:
                    return f"No sleep data for {date}."
        else:
            data = _load_json(DERIVED_DIR / "sleep.json")
        return _format_sleep(data)
    elif action == "all":
        return _format_all(date)
    else:
        return f"Unknown action: {action}"
