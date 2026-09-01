"""Command-line interface for git-radial-history."""

from __future__ import annotations

import argparse
import sys
from datetime import date
from pathlib import Path

from git_radial_history import __version__
from git_radial_history.config import Config, load_config
from git_radial_history.history import analyse
from git_radial_history.model import Analysis, RadialHistoryError
from git_radial_history.repository import acquire
from git_radial_history.svg import render_svg


def _err(message: str) -> None:
    print(f"error: {message}", file=sys.stderr)


def _log(message: str) -> None:
    print(message, file=sys.stderr)


_TAG_ORDER = ("major", "minor", "patch")


def _levels_from_threshold(level: str) -> tuple[str, ...]:
    """Return the given release level and every more-important level."""
    return _TAG_ORDER[: _TAG_ORDER.index(level) + 1]


def _apply_tag_threshold(config: Config, level: str | None, *, from_config: bool) -> Config:
    """Apply the --tags threshold, respecting CLI-over-config precedence.

    An explicit --tags flag always wins. Otherwise a config file's own [tags]
    levels are honoured. With neither, the effective default is "minor" (major
    and minor releases).
    """
    from dataclasses import replace

    if level is None:
        if from_config:
            return config
        level = "minor"
    levels = _levels_from_threshold(level)
    return replace(config, tags=replace(config.tags, levels=levels))


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="git-radial-history",
        description="Generate an offline radial history poster from a Git repository.",
    )
    parser.add_argument("source", metavar="SOURCE", help="Local path or Git remote URL")
    parser.add_argument("--ref", default="HEAD", help="Revision or branch (default: HEAD)")
    parser.add_argument("--output", help="Output basename (default: repository name)")
    parser.add_argument(
        "--format",
        choices=("svg", "png", "both"),
        default="both",
        help="Output format(s) (default: both)",
    )
    parser.add_argument("--config", type=Path, help="TOML configuration file")
    parser.add_argument(
        "--tags",
        choices=("major", "minor", "patch"),
        default=None,
        help="Lowest release level to show, and above (default: minor)",
    )
    parser.add_argument("--title", help="Override the inferred repository name")
    parser.add_argument("--refresh", action="store_true", help="Re-fetch a cached remote")
    parser.add_argument("--from", dest="from_date", help="Limit start date (YYYY-MM-DD)")
    parser.add_argument("--until", dest="until_date", help="Limit end date (YYYY-MM-DD)")
    parser.add_argument("--scale", type=float, default=1.0, help="PNG raster scale factor")
    parser.add_argument("--version", action="version", version=f"%(prog)s {__version__}")
    return parser


def _parse_date(value: str | None, label: str) -> date | None:
    if value is None:
        return None
    try:
        return date.fromisoformat(value)
    except ValueError as exc:
        raise RadialHistoryError(f"Invalid --{label} date: {value!r}") from exc


def _filter_dates(analysis: Analysis, start: date | None, end: date | None) -> Analysis:
    if start is None and end is None:
        return analysis
    if start and end and start > end:
        raise RadialHistoryError("--from date must not be after --until date.")

    kept = [
        d
        for d in analysis.days
        if (start is None or d.date >= start) and (end is None or d.date <= end)
    ]
    dropped = len(analysis.days) - len(kept)
    if dropped:
        _log(f"warning: {dropped} active day(s) fall outside the requested range.")

    earliest = min((d.date for d in kept), default=None)
    latest = max((d.date for d in kept), default=None)
    from dataclasses import replace

    return replace(analysis, days=tuple(kept), earliest_date=earliest, latest_date=latest)


def _warn(analysis: Analysis, config: Config) -> None:
    if analysis.binary_records:
        _log(f"warning: {analysis.binary_records} binary-file record(s) omitted from line counts.")
    if analysis.root_count > 1:
        _log(f"warning: {analysis.root_count} root commits found; using the earliest.")


def run(argv: list[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)

    config = load_config(args.config)
    config = _apply_tag_threshold(config, args.tags, from_config=args.config is not None)
    start = _parse_date(args.from_date, "from")
    end = _parse_date(args.until_date, "until")

    repo = acquire(
        args.source,
        args.ref,
        refresh=args.refresh,
    )
    analysis = analyse(repo)

    if args.title:
        from dataclasses import replace

        analysis = replace(analysis, repository_name=args.title)

    analysis = _filter_dates(analysis, start, end)
    _warn(analysis, config)

    basename = args.output or analysis.repository_name
    output_dir = Path("output")
    output_dir.mkdir(parents=True, exist_ok=True)
    outputs: list[Path] = []

    svg = render_svg(analysis, config)

    if args.format in ("svg", "both"):
        svg_path = output_dir / f"{basename}.svg"
        svg_path.write_text(svg, encoding="utf-8")
        outputs.append(svg_path)

    if args.format in ("png", "both"):
        from git_radial_history.raster import render_png

        png = render_png(svg, scale=args.scale)
        png_path = output_dir / f"{basename}.png"
        png_path.write_bytes(png)
        outputs.append(png_path)

    for path in outputs:
        print(path)

    return 0


def main(argv: list[str] | None = None) -> int:
    try:
        return run(argv)
    except RadialHistoryError as exc:
        _err(str(exc))
        return 1
    except KeyboardInterrupt:  # pragma: no cover
        _err("interrupted")
        return 130


if __name__ == "__main__":
    raise SystemExit(main())
