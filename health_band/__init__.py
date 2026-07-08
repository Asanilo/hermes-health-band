"""Health Band plugin for Hermes.

Registers health_band tool for reading smart band health data
via Gadgetbridge sync.
"""
from __future__ import annotations

from typing import Any


def register(ctx: Any) -> None:
    """Register health band tools. Called once by the plugin loader."""
    from .tools import (
        HEALTH_BAND_SCHEMA,
        _check_health_band_available,
        _handle_health_band,
    )

    ctx.register_tool(
        name="health_band",
        toolset="health_band",
        schema=HEALTH_BAND_SCHEMA,
        handler=_handle_health_band,
        check_fn=_check_health_band_available,
        emoji="❤️",
    )
