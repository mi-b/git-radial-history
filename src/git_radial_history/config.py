"""TOML configuration parsing with strict key validation."""

from __future__ import annotations

import tomllib
from dataclasses import dataclass, field, fields
from pathlib import Path
from typing import Any

from git_radial_history.model import RadialHistoryError


@dataclass(frozen=True)
class PosterConfig:
    width: int = 2400
    height: int = 2400
    background: str = "#1e1e2e"
    positive: str = "#b4befe"
    negative: str = "#f5e0dc"
    accent: str = "#f38ba8"
    text: str = "#cdd6f4"
    show_year_labels: bool = False


@dataclass(frozen=True)
class LayoutConfig:
    inner_radius_ratio: float = 0.28
    outer_radius_ratio: float = 0.90
    chart_height_ratio: float = 1.0


@dataclass(frozen=True)
class ScaleConfig:
    percentile: int = 99
    maximum_radius: float = 0.0


@dataclass(frozen=True)
class TagsConfig:
    show: bool = True
    show_unrecognised: bool = False
    show_prerelease: bool = False
    levels: tuple[str, ...] = ("major", "minor", "patch")


@dataclass(frozen=True)
class Config:
    poster: PosterConfig = field(default_factory=PosterConfig)
    layout: LayoutConfig = field(default_factory=LayoutConfig)
    scale: ScaleConfig = field(default_factory=ScaleConfig)
    tags: TagsConfig = field(default_factory=TagsConfig)


_SECTIONS = {
    "poster": PosterConfig,
    "layout": LayoutConfig,
    "scale": ScaleConfig,
    "tags": TagsConfig,
}


def _build_section(name: str, cls: type[Any], data: dict) -> Any:
    allowed = {f.name for f in fields(cls)}
    unknown = set(data) - allowed
    if unknown:
        raise RadialHistoryError(f"Unknown key(s) in [{name}]: {', '.join(sorted(unknown))}")
    if name == "tags" and "levels" in data:
        data = {**data, "levels": _validate_levels(data["levels"])}
    return cls(**data)


_VALID_LEVELS = ("major", "minor", "patch")


def _validate_levels(value: object) -> tuple[str, ...]:
    if not isinstance(value, list) or not all(isinstance(v, str) for v in value):
        raise RadialHistoryError("[tags] levels must be a list of strings.")
    invalid = [v for v in value if v not in _VALID_LEVELS]
    if invalid:
        raise RadialHistoryError(
            f"[tags] levels contains invalid value(s): {', '.join(invalid)}. "
            f"Choose from: {', '.join(_VALID_LEVELS)}."
        )
    return tuple(value)


def load_config(path: Path | None) -> Config:
    """Load configuration from TOML, rejecting unknown sections and keys."""
    if path is None:
        return Config()

    if not path.exists():
        raise RadialHistoryError(f"Configuration file not found: {path}")

    try:
        raw = tomllib.loads(path.read_text(encoding="utf-8"))
    except tomllib.TOMLDecodeError as exc:
        raise RadialHistoryError(f"Invalid TOML in {path}: {exc}") from exc

    unknown_sections = set(raw) - set(_SECTIONS)
    if unknown_sections:
        raise RadialHistoryError(
            f"Unknown configuration section(s): {', '.join(sorted(unknown_sections))}"
        )

    sections = {
        name: _build_section(name, cls, raw.get(name, {})) for name, cls in _SECTIONS.items()
    }
    return Config(**sections)
