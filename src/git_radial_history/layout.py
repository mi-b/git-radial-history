"""Radial geometry, marker scaling, and legend value selection."""

from __future__ import annotations

import calendar
import math
from dataclasses import dataclass
from datetime import date

from git_radial_history.config import Config
from git_radial_history.model import Analysis, DailyChange


def day_of_year_index(day: date) -> int:
    """Zero-based index of the day within its calendar year."""
    return day.timetuple().tm_yday - 1


def days_in_year(year: int) -> int:
    return 366 if calendar.isleap(year) else 365


def day_angle(day: date) -> float:
    """Angle in radians. January starts at 12 o'clock; dates advance clockwise."""
    index = day_of_year_index(day)
    total = days_in_year(day.year)
    return -math.pi / 2 + 2 * math.pi * index / total


@dataclass(frozen=True)
class Geometry:
    centre_x: float
    centre_y: float
    inner_radius: float
    outer_radius: float
    track_spacing: float
    first_year: int
    year_count: int

    def year_radius(self, year: int) -> float:
        return self.inner_radius + (year - self.first_year) * self.track_spacing

    def radius_for(self, day: date) -> float:
        """Radius that grows continuously through the year, forming a spiral."""
        year_fraction = day_of_year_index(day) / days_in_year(day.year)
        position = (day.year - self.first_year) + year_fraction
        return self.inner_radius + position * self.track_spacing

    def point(self, day: date) -> tuple[float, float]:
        radius = self.radius_for(day)
        angle = day_angle(day)
        return (
            self.centre_x + radius * math.cos(angle),
            self.centre_y + radius * math.sin(angle),
        )


def build_geometry(analysis: Analysis, config: Config) -> Geometry:
    poster = config.poster
    layout = config.layout

    chart_height = poster.height * layout.chart_height_ratio
    chart_size = min(poster.width, chart_height)
    max_radius = chart_size / 2

    inner_radius = max_radius * layout.inner_radius_ratio
    outer_radius = max_radius * layout.outer_radius_ratio

    if analysis.earliest_date is None or analysis.latest_date is None:
        first_year = date.today().year
        year_count = 1
    else:
        first_year = analysis.earliest_date.year
        year_count = analysis.latest_date.year - first_year + 1

    if year_count > 1:
        track_spacing = (outer_radius - inner_radius) / (year_count - 1)
    else:
        track_spacing = outer_radius - inner_radius

    centre_x = poster.width / 2
    centre_y = chart_height / 2

    return Geometry(
        centre_x=centre_x,
        centre_y=centre_y,
        inner_radius=inner_radius,
        outer_radius=outer_radius,
        track_spacing=track_spacing,
        first_year=first_year,
        year_count=year_count,
    )


def _percentile(values: list[int], percentile: float) -> float:
    if not values:
        return 1.0
    ordered = sorted(values)
    if len(ordered) == 1:
        return float(ordered[0])
    rank = (percentile / 100) * (len(ordered) - 1)
    lower = math.floor(rank)
    upper = math.ceil(rank)
    if lower == upper:
        return float(ordered[lower])
    weight = rank - lower
    return ordered[lower] * (1 - weight) + ordered[upper] * weight


@dataclass(frozen=True)
class Scale:
    scale_factor: float
    reference_value: float
    max_marker_radius: float
    capped: bool

    def marker_radius(self, net_lines: int) -> float:
        radius = self.scale_factor * math.sqrt(abs(net_lines))
        if self.max_marker_radius > 0:
            return min(radius, self.max_marker_radius)
        return radius


def build_scale(analysis: Analysis, config: Config, geometry: Geometry) -> Scale:
    magnitudes = [abs(d.net_lines) for d in analysis.days if d.net_lines != 0]
    scale_cfg = config.scale

    reference = _percentile(magnitudes, scale_cfg.percentile) if magnitudes else 1.0
    reference = max(reference, 1.0)

    # Target: a reference-magnitude marker fills a fraction of the track spacing.
    target_radius = geometry.track_spacing * 0.45
    scale_factor = target_radius / math.sqrt(reference)

    capped = scale_cfg.maximum_radius > 0
    return Scale(
        scale_factor=scale_factor,
        reference_value=reference,
        max_marker_radius=scale_cfg.maximum_radius,
        capped=capped,
    )


def legend_values(reference: float, count: int = 3) -> list[int]:
    """Produce a readable ascending sequence from the 1, 2, 5 x 10^n family."""
    if reference <= 0:
        return [1]
    steps = [1, 2, 5]
    values: list[int] = []
    magnitude = math.floor(math.log10(reference))
    # Walk downwards from the reference to gather `count` nice values.
    candidates: list[int] = []
    exp = magnitude + 1
    while len(candidates) < count * 3 and exp >= -1:
        for s in reversed(steps):
            value = int(s * (10**exp))
            if value >= 1 and value <= reference * 2:
                candidates.append(value)
        exp -= 1
    candidates = sorted(set(candidates))
    if not candidates:
        return [1]
    values = candidates[-count:]
    return values


@dataclass(frozen=True)
class TagMarker:
    day: DailyChange
    tag: str
    offset_index: int
    is_semantic: bool
    level: str  # "major", "minor", "patch", "other"


_SEMVER = None


def classify_tag(tag: str) -> tuple[bool, str]:
    """Classify a tag as semantic and assign a level.

    Levels: "major", "minor", "patch", "prerelease" (semver-shaped tags with a
    pre-release suffix such as -rc1/-alpha/-beta), or "other" (non-semver).
    """
    import re

    global _SEMVER
    if _SEMVER is None:
        _SEMVER = re.compile(r"^v?(\d+)\.(\d+)(?:\.(\d+))?(?P<pre>[-.].+)?$")
    match = _SEMVER.match(tag)
    if not match:
        return False, "other"
    if match.group("pre"):
        return True, "prerelease"
    minor = int(match.group(2))
    patch = int(match.group(3)) if match.group(3) else 0
    if patch != 0:
        return True, "patch"
    if minor != 0:
        return True, "minor"
    return True, "major"


def tag_markers(analysis: Analysis, config: Config) -> list[TagMarker]:
    markers: list[TagMarker] = []
    allowed_levels = set(config.tags.levels)
    for day in analysis.days:
        offset = 0
        for tag in day.tags:
            is_semantic, level = classify_tag(tag)
            if not is_semantic:
                if not config.tags.show_unrecognised:
                    continue
            elif level == "prerelease":
                if not config.tags.show_prerelease:
                    continue
            elif level not in allowed_levels:
                continue
            markers.append(
                TagMarker(
                    day=day,
                    tag=tag,
                    offset_index=offset,
                    is_semantic=is_semantic,
                    level=level,
                )
            )
            offset += 1
    return markers
