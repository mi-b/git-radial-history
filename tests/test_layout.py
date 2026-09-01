from __future__ import annotations

import math
from datetime import date

from git_radial_history.config import Config
from git_radial_history.layout import (
    build_geometry,
    classify_tag,
    day_angle,
    days_in_year,
    legend_values,
)
from git_radial_history.model import Analysis, DailyChange


def _analysis(first: date, last: date) -> Analysis:
    return Analysis(
        schema_version=1,
        source="x",
        ref="HEAD",
        commit_hash="0" * 40,
        repository_name="x",
        root=None,
        root_count=0,
        earliest_date=first,
        latest_date=last,
        total_commits=1,
        binary_records=0,
        days=(),
    )


def test_january_at_twelve_oclock():
    # 1 January -> angle -pi/2 (top of circle).
    assert math.isclose(day_angle(date(2021, 1, 1)), -math.pi / 2)


def test_clockwise_progression():
    jan = day_angle(date(2021, 1, 1))
    apr = day_angle(date(2021, 4, 1))
    assert apr > jan  # increasing angle = clockwise in SVG coords


def test_leap_year_days():
    assert days_in_year(2020) == 366
    assert days_in_year(2021) == 365


def test_year_to_radius_mapping():
    config = Config()
    geo = build_geometry(_analysis(date(2019, 1, 1), date(2023, 1, 1)), config)
    assert geo.year_count == 5
    assert geo.year_radius(2019) == geo.inner_radius
    assert math.isclose(geo.year_radius(2023), geo.outer_radius)
    # Increasing year => increasing radius.
    assert geo.year_radius(2020) > geo.year_radius(2019)


def test_single_year_geometry():
    config = Config()
    geo = build_geometry(_analysis(date(2021, 1, 1), date(2021, 12, 31)), config)
    assert geo.year_count == 1


def test_legend_values_ascending_and_nice():
    values = legend_values(4200)
    assert values == sorted(values)
    steps = {int(str(v)[0]) for v in values}
    assert steps <= {1, 2, 5}


def test_classify_tag():
    assert classify_tag("v1.0.0") == (True, "major")
    assert classify_tag("v1.2.0") == (True, "minor")
    assert classify_tag("v1.2.3") == (True, "patch")
    assert classify_tag("nightly") == (False, "other")


def test_classify_prerelease():
    assert classify_tag("v2.40.0-rc1") == (True, "prerelease")
    assert classify_tag("v1.0.0-alpha") == (True, "prerelease")
    assert classify_tag("2.0.0-beta.2") == (True, "prerelease")


def _tag_analysis() -> Analysis:
    from git_radial_history.model import DailyChange

    days = (
        DailyChange(
            date(2021, 1, 1),
            0,
            0,
            5,
            1,
            (),
            ("v2.0.0", "v2.1.0", "v2.1.3", "v2.2.0-rc1", "nightly"),
        ),
    )
    return Analysis(
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


def test_tag_levels_filter_major_only():
    from git_radial_history.config import Config, TagsConfig
    from git_radial_history.layout import tag_markers

    config = Config(tags=TagsConfig(levels=("major",)))
    markers = tag_markers(_tag_analysis(), config)
    assert [m.tag for m in markers] == ["v2.0.0"]


def test_tag_levels_major_and_minor():
    from git_radial_history.config import Config, TagsConfig
    from git_radial_history.layout import tag_markers

    config = Config(tags=TagsConfig(levels=("major", "minor")))
    markers = tag_markers(_tag_analysis(), config)
    assert [m.tag for m in markers] == ["v2.0.0", "v2.1.0"]


def test_prerelease_hidden_by_default():
    from git_radial_history.config import Config
    from git_radial_history.layout import tag_markers

    markers = tag_markers(_tag_analysis(), Config())
    tags = [m.tag for m in markers]
    assert "v2.2.0-rc1" not in tags
    assert "nightly" not in tags
    assert tags == ["v2.0.0", "v2.1.0", "v2.1.3"]


def test_prerelease_shown_when_enabled():
    from git_radial_history.config import Config, TagsConfig
    from git_radial_history.layout import tag_markers

    config = Config(tags=TagsConfig(show_prerelease=True))
    markers = tag_markers(_tag_analysis(), config)
    assert "v2.2.0-rc1" in [m.tag for m in markers]


def test_circle_area_ratio():
    from git_radial_history.layout import build_scale

    config = Config()
    days = tuple(
        DailyChange(date(2021, 1, i + 1), 0, 0, n, 1, (), ()) for i, n in enumerate([1, 4, 100])
    )
    analysis = Analysis(
        1,
        "x",
        "HEAD",
        "0" * 40,
        "x",
        None,
        0,
        date(2021, 1, 1),
        date(2021, 1, 3),
        3,
        0,
        days,
    )
    geo = build_geometry(analysis, config)
    scale = build_scale(analysis, config, geo)
    # sqrt scaling: radius(4) / radius(1) == 2.
    assert math.isclose(scale.marker_radius(4) / scale.marker_radius(1), 2.0)
