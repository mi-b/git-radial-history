"""Self-contained, deterministic SVG poster rendering."""

from __future__ import annotations

import calendar
import math
import xml.etree.ElementTree as ET

from git_radial_history.config import Config
from git_radial_history.layout import (
    Geometry,
    Scale,
    TagMarker,
    build_geometry,
    build_scale,
    day_angle,
    legend_values,
    tag_markers,
)
from git_radial_history.model import Analysis

SANS_FAMILY = "Fira Sans"
MONO_FAMILY = "Fira Mono"


def _fmt(value: float) -> str:
    """Deterministic, compact float formatting for stable diffs."""
    return f"{value:.3f}".rstrip("0").rstrip(".")


def _short_number(value: int) -> str:
    """Format a legend value compactly, e.g. 1000 -> '1k', 1500000 -> '1.5M'."""
    for threshold, suffix in ((1_000_000_000, "B"), (1_000_000, "M"), (1_000, "k")):
        if abs(value) >= threshold:
            scaled = value / threshold
            text = f"{scaled:.1f}".rstrip("0").rstrip(".")
            return f"{text}{suffix}"
    return str(value)


def _sub(parent: ET.Element, tag: str, **attrs: object) -> ET.Element:
    element = ET.SubElement(parent, tag)
    for key, value in attrs.items():
        name = key.rstrip("_").replace("_", "-")
        element.set(name, str(value))
    return element


def _render_months(group: ET.Element, geo: Geometry, config: Config) -> None:
    label_radius = geo.outer_radius + geo.track_spacing * 1.3

    for month in range(12):
        angle = -math.pi / 2 + 2 * math.pi * (month / 12)
        x = geo.centre_x + label_radius * math.cos(angle)
        y = geo.centre_y + label_radius * math.sin(angle)
        text = _sub(
            group,
            "text",
            x=_fmt(x),
            y=_fmt(y),
            fill=config.poster.text,
            font_family=SANS_FAMILY,
            font_size=28,
            text_anchor="middle",
            dominant_baseline="middle",
        )
        text.text = calendar.month_abbr[month + 1]


def _render_changes(
    group: ET.Element,
    analysis: Analysis,
    geo: Geometry,
    scale: Scale,
    config: Config,
) -> None:
    for day in analysis.days:
        x, y = geo.point(day.date)
        title_text = (
            f"{day.date.isoformat()}: +{day.additions} -{day.deletions} "
            f"({day.commit_count} commit{'s' if day.commit_count != 1 else ''})"
        )
        if day.net_lines > 0:
            radius = scale.marker_radius(day.net_lines)
            circle = _sub(
                group,
                "circle",
                cx=_fmt(x),
                cy=_fmt(y),
                r=_fmt(radius),
                fill=config.poster.positive,
                fill_opacity=0.85,
            )
        elif day.net_lines < 0:
            radius = scale.marker_radius(day.net_lines)
            circle = _sub(
                group,
                "circle",
                cx=_fmt(x),
                cy=_fmt(y),
                r=_fmt(radius),
                fill="none",
                stroke=config.poster.negative,
                stroke_width=3,
            )
        else:
            circle = _sub(
                group,
                "circle",
                cx=_fmt(x),
                cy=_fmt(y),
                r=2.5,
                fill=config.poster.text,
                fill_opacity=0.5,
            )
        ET.SubElement(circle, "title").text = title_text


def _render_tags(
    group: ET.Element, markers: list[TagMarker], geo: Geometry, config: Config
) -> None:
    for marker in markers:
        day = marker.day.date
        radius = geo.radius_for(day) + marker.offset_index * 14
        angle = day_angle(day)

        size = {"major": 15, "minor": 11, "patch": 6, "prerelease": 5, "other": 8}[marker.level]
        # Triangle pointing radially outward, sized in absolute pixels so that
        # markers of the same level look identical regardless of ring radius.
        cx = geo.centre_x + radius * math.cos(angle)
        cy = geo.centre_y + radius * math.sin(angle)
        # Unit vectors: radial (outward) and tangential (perpendicular).
        rx, ry = math.cos(angle), math.sin(angle)
        tx, ty = -ry, rx
        # Equilateral triangle: height = 1.5*size, base = height * 2/sqrt(3).
        half_base = (1.5 * size) / math.sqrt(3)
        tip = (cx + rx * size, cy + ry * size)
        left = (cx - rx * (size / 2) - tx * half_base, cy - ry * (size / 2) - ty * half_base)
        right = (cx - rx * (size / 2) + tx * half_base, cy - ry * (size / 2) + ty * half_base)
        points = " ".join(f"{_fmt(px)},{_fmt(py)}" for px, py in (tip, left, right))
        # Major = solid, minor/patch = outlined (patch is drawn smaller via size).
        accent = config.poster.accent
        if marker.level == "major":
            style: dict[str, object] = {"fill": accent}
        else:
            style = {"fill": "none", "stroke": accent, "stroke_width": 2}
        polygon = _sub(group, "polygon", points=points, **style)
        ET.SubElement(polygon, "title").text = marker.tag


def _render_annotation(
    group: ET.Element, analysis: Analysis, geo: Geometry, config: Config
) -> None:
    lines: list[tuple[str, bool]] = [(analysis.repository_name, True)]

    if analysis.earliest_date and analysis.latest_date:
        date_range = (
            f"{analysis.earliest_date.isoformat()} until {analysis.latest_date.isoformat()}"
        )
        lines.append((date_range, False))

    if not lines:
        return

    # Centre the block of lines vertically on the poster centre.
    line_height = 44
    start_y = geo.centre_y - (len(lines) - 1) * line_height / 2
    for index, (line, is_title) in enumerate(lines):
        text = _sub(
            group,
            "text",
            x=_fmt(geo.centre_x),
            y=_fmt(start_y + index * line_height),
            fill=config.poster.text,
            font_family=SANS_FAMILY,
            font_size=34 if is_title else 26,
            font_style="italic" if is_title else "normal",
            text_anchor="middle",
            dominant_baseline="middle",
        )
        text.text = line


def _render_legend(root: ET.Element, analysis: Analysis, scale: Scale, config: Config) -> None:
    poster = config.poster
    group = _sub(root, "g", id="legend")

    # Compact key in the bottom-left corner, echoing Palmer's matrix layout.
    origin_x = poster.width * 0.8
    origin_y = poster.height * 0.9

    values = legend_values(scale.reference_value)
    radii = [scale.marker_radius(v) for v in values]
    max_radius = max(radii) if radii else 0.0

    # Rows are stacked top (smallest) to bottom (largest). Row spacing keeps the
    # largest circles from touching.
    row_gap = max_radius * 2 + 22
    label_x = origin_x
    # Circle columns and triangle keys share one horizontal spacing so their
    # centrelines are equally spaced.
    col_spacing = max_radius * 2 + 50
    filled_cx = origin_x + max_radius + 70
    outlined_cx = filled_cx + col_spacing

    for index, (value, radius) in enumerate(zip(values, radii, strict=True)):
        cy = origin_y + index * row_gap

        # Right-aligned numeric label with compact k/M suffixes.
        label = _sub(
            group,
            "text",
            x=_fmt(label_x + max_radius),
            y=_fmt(cy + 8),
            fill=poster.text,
            font_family=MONO_FAMILY,
            font_size=24,
            text_anchor="end",
        )
        label.text = _short_number(value)

        # Filled column = positive net change.
        _sub(
            group,
            "circle",
            cx=_fmt(filled_cx),
            cy=_fmt(cy),
            r=_fmt(radius),
            fill=poster.positive,
            fill_opacity=0.85,
        )
        # Outlined column = negative net change.
        _sub(
            group,
            "circle",
            cx=_fmt(outlined_cx),
            cy=_fmt(cy),
            r=_fmt(radius),
            fill="none",
            stroke=poster.negative,
            stroke_width=2,
        )

    caption_y = origin_y + max(len(values) - 1, 0) * row_gap + max_radius + 40
    for cx, text in ((filled_cx, "+++"), (outlined_cx, "---")):
        caption = _sub(
            group,
            "text",
            x=_fmt(cx),
            y=_fmt(caption_y),
            fill=poster.text,
            font_family=MONO_FAMILY,
            font_size=26,
            text_anchor="middle",
            fill_opacity=0.85,
        )
        caption.text = text

    # Tag key to the right of the circle matrix, only when tags are shown.
    has_tags = config.tags.show and any(d.tags for d in analysis.days)
    if has_tags:
        tri_cx = outlined_cx + col_spacing
        # Legend triangle sizes echo the chart's per-level sizing (major biggest,
        # patch clearly the smallest).
        tri_sizes = {"major": 22, "minor": 16, "patch": 9}
        max_tri = max(tri_sizes.values())
        # Stack the tag levels vertically, bottom-aligned with the largest
        # (bottom-row) circle so the columns share a baseline.
        levels = [lvl for lvl in ("major", "minor", "patch") if lvl in config.tags.levels]
        circles_bottom = origin_y + max(len(values) - 1, 0) * row_gap + max_radius
        label_offset_x = max_tri + 24

        for stack_index, level in enumerate(levels):
            tri_size = tri_sizes[level]
            # Equilateral triangle: half-base b, height b*sqrt(3), centred on tri_y.
            half_base = tri_size
            height = half_base * math.sqrt(3)
            # Bottom level sits on the largest circle's baseline; higher levels
            # climb by one row_gap each.
            tri_bottom = circles_bottom - stack_index * row_gap
            tri_y = tri_bottom - height / 2
            points = " ".join(
                [
                    f"{_fmt(tri_cx)},{_fmt(tri_y - height / 2)}",
                    f"{_fmt(tri_cx - half_base)},{_fmt(tri_y + height / 2)}",
                    f"{_fmt(tri_cx + half_base)},{_fmt(tri_y + height / 2)}",
                ]
            )
            if level == "major":
                _sub(group, "polygon", points=points, fill=poster.accent)
            else:
                _sub(
                    group,
                    "polygon",
                    points=points,
                    fill="none",
                    stroke=poster.accent,
                    stroke_width=2,
                )
            level_label = _sub(
                group,
                "text",
                x=_fmt(tri_cx + label_offset_x),
                y=_fmt(tri_y + 6),
                fill=poster.text,
                font_family=SANS_FAMILY,
                font_size=22,
                text_anchor="start",
                fill_opacity=0.85,
            )
            level_label.text = level

        tags_caption = _sub(
            group,
            "text",
            x=_fmt(tri_cx),
            y=_fmt(caption_y),
            fill=poster.text,
            font_family=SANS_FAMILY,
            font_size=22,
            text_anchor="middle",
            fill_opacity=0.85,
        )
        tags_caption.text = "tags"


def render_svg(analysis: Analysis, config: Config) -> str:
    """Render the analysis into a deterministic, self-contained SVG string."""
    poster = config.poster
    geo = build_geometry(analysis, config)
    scale = build_scale(analysis, config, geo)
    markers = tag_markers(analysis, config) if config.tags.show else []

    svg = ET.Element(
        "svg",
        {
            "xmlns": "http://www.w3.org/2000/svg",
            "width": str(poster.width),
            "height": str(poster.height),
            "viewBox": f"0 0 {poster.width} {poster.height}",
            "role": "img",
        },
    )

    ET.SubElement(svg, "title").text = f"Radial commit history of {analysis.repository_name}"
    desc = ET.SubElement(svg, "desc")
    desc.text = f"Radial visualisation of daily net line changes for {analysis.repository_name}"

    _sub(
        svg,
        "rect",
        x=0,
        y=0,
        width=poster.width,
        height=poster.height,
        fill=poster.background,
    )

    months = _sub(svg, "g", id="months")
    _render_months(months, geo, config)

    if poster.show_year_labels:
        years = _sub(svg, "g", id="years")
        for year in range(geo.first_year, geo.first_year + geo.year_count):
            label = _sub(
                years,
                "text",
                x=_fmt(geo.centre_x),
                y=_fmt(geo.centre_y - geo.year_radius(year)),
                fill=poster.text,
                font_family=SANS_FAMILY,
                font_size=18,
                text_anchor="middle",
                fill_opacity=0.5,
            )
            label.text = str(year)

    changes = _sub(svg, "g", id="changes")
    _render_changes(changes, analysis, geo, scale, config)

    tags_group = _sub(svg, "g", id="tags")
    _render_tags(tags_group, markers, geo, config)

    annotation = _sub(svg, "g", id="annotation")
    _render_annotation(annotation, analysis, geo, config)

    _render_legend(svg, analysis, scale, config)

    return _serialise(svg)


def _serialise(svg: ET.Element) -> str:
    ET.indent(svg, space="  ")
    body = ET.tostring(svg, encoding="unicode")
    return '<?xml version="1.0" encoding="UTF-8"?>\n' + body + "\n"
