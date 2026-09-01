from __future__ import annotations

import xml.etree.ElementTree as ET

from git_radial_history.config import Config
from git_radial_history.history import extract
from git_radial_history.repository import acquire
from git_radial_history.svg import render_svg

NS = "{http://www.w3.org/2000/svg}"


def _svg(sample_repo, config=None):
    repo = acquire(str(sample_repo), "HEAD")
    analysis = extract(repo)
    return analysis, render_svg(analysis, config or Config())


def test_valid_xml(sample_repo):
    _, svg = _svg(sample_repo)
    root = ET.fromstring(svg)
    assert root.tag == f"{NS}svg"


def test_dimensions_and_viewbox(sample_repo):
    config = Config()
    _, svg = _svg(sample_repo, config)
    root = ET.fromstring(svg)
    assert root.get("width") == str(config.poster.width)
    assert root.get("height") == str(config.poster.height)
    assert root.get("viewBox") == f"0 0 {config.poster.width} {config.poster.height}"


def test_semantic_groups_present(sample_repo):
    _, svg = _svg(sample_repo)
    root = ET.fromstring(svg)
    ids = {g.get("id") for g in root.iter(f"{NS}g")}
    assert {"months", "changes", "tags", "annotation", "legend"} <= ids


def test_marker_count_matches_active_days(sample_repo):
    analysis, svg = _svg(sample_repo)
    root = ET.fromstring(svg)
    changes = next(g for g in root.iter(f"{NS}g") if g.get("id") == "changes")
    circles = changes.findall(f"{NS}circle")
    assert len(circles) == len(analysis.days)


def test_deterministic(sample_repo):
    _, a = _svg(sample_repo)
    _, b = _svg(sample_repo)
    assert a == b
    assert "timestamp" not in a.lower()


def test_tag_marker_rendered(sample_repo):
    _, svg = _svg(sample_repo)
    root = ET.fromstring(svg)
    tags = next(g for g in root.iter(f"{NS}g") if g.get("id") == "tags")
    polygons = tags.findall(f"{NS}polygon")
    assert len(polygons) == 1
    title = polygons[0].find(f"{NS}title")
    assert title is not None
    assert title.text == "v1.0.0"
    # v1.0.0 is a major release: solid fill, no stroke.
    assert polygons[0].get("fill") == Config().poster.accent
    assert polygons[0].get("stroke") is None


def test_minor_tag_is_outlined():
    from datetime import date

    from git_radial_history.config import Config, TagsConfig
    from git_radial_history.model import Analysis, DailyChange

    days = (DailyChange(date(2021, 1, 1), 5, 0, 5, 1, (), ("v1.2.0",)),)
    analysis = Analysis(
        1,
        "x",
        "HEAD",
        "0" * 40,
        "x",
        None,
        0,
        date(2021, 1, 1),
        date(2021, 1, 1),
        1,
        0,
        days,
    )
    config = Config(tags=TagsConfig(levels=("major", "minor")))
    svg = render_svg(analysis, config)
    root = ET.fromstring(svg)
    tags = next(g for g in root.iter(f"{NS}g") if g.get("id") == "tags")
    polygon = tags.findall(f"{NS}polygon")[0]
    assert polygon.get("fill") == "none"
    assert polygon.get("stroke") == Config().poster.accent


def test_accessibility_metadata(sample_repo):
    _, svg = _svg(sample_repo)
    root = ET.fromstring(svg)
    assert root.find(f"{NS}title") is not None
    assert root.find(f"{NS}desc") is not None
