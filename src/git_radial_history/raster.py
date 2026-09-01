"""Rasterise the canonical SVG to PNG via resvg-py."""

from __future__ import annotations

from git_radial_history.model import RadialHistoryError


def render_png(svg: str, scale: float = 1.0) -> bytes:
    """Rasterise an SVG string to PNG bytes.

    The SVG is treated as canonical; layout is never duplicated here.
    """
    try:
        import resvg_py
    except ImportError as exc:  # pragma: no cover
        raise RadialHistoryError(
            "PNG output requires the 'resvg-py' package. Install it or use --format svg."
        ) from exc

    try:
        result = resvg_py.svg_to_bytes(svg_string=svg, zoom=scale)
    except TypeError:
        # Older/newer signatures may differ; try the simple form.
        result = resvg_py.svg_to_bytes(svg)  # type: ignore[call-arg]

    if isinstance(result, list):
        return bytes(result)
    return bytes(result)
