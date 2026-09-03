from datetime import date

# Categorical slots 1 (blue) and 2 (orange) from the validated palette — passes the
# CVD adjacent-pair floor, so the two trend charts stay distinguishable at a glance.
COLOR_CLICKS = "#2a78d6"
COLOR_CONVERSIONS = "#eb6834"

_SURFACE = "#fcfcfb"
_GRIDLINE = "#e1e0d9"
_BASELINE = "#c3c2b7"
_MUTED = "#898781"
_SECONDARY_INK = "#52514e"


def _fmt_date(d: date) -> str:
    # strftime's no-leading-zero day ("%-d") isn't portable to Windows; build it by hand.
    return f"{d.strftime('%b')} {d.day}"


def build_trend_chart(series: list[tuple[date, int]], color: str, width: int = 600, height: int = 140) -> str:
    """Render a single-series area/line trend chart as an inline SVG string.

    One measure, one axis, one hue — two different-scale measures (clicks vs.
    conversions) get two of these side by side rather than a dual-axis chart.
    """
    pad_left, pad_right, pad_top, pad_bottom = 8, 8, 14, 22
    plot_w = width - pad_left - pad_right
    plot_h = height - pad_top - pad_bottom
    baseline_y = pad_top + plot_h

    n = len(series)
    max_val = max((v for _, v in series), default=0) or 1

    if n == 0:
        return f'<svg viewBox="0 0 {width} {height}" width="100%" height="{height}"></svg>'

    if n == 1:
        d, v = series[0]
        x, y = pad_left + plot_w / 2, baseline_y - (plot_h * v / max_val)
        return (
            f'<svg viewBox="0 0 {width} {height}" width="100%" height="{height}" role="img">'
            f'<line x1="{pad_left}" y1="{baseline_y:.1f}" x2="{width - pad_right}" y2="{baseline_y:.1f}" '
            f'stroke="{_BASELINE}" stroke-width="1" />'
            f'<circle cx="{x:.1f}" cy="{y:.1f}" r="4" fill="{color}" stroke="{_SURFACE}" stroke-width="2">'
            f"<title>{_fmt_date(d)}: {v}</title></circle>"
            f'<text x="{x:.1f}" y="{max(y - 10, 12):.1f}" text-anchor="middle" font-size="11" fill="{_SECONDARY_INK}">{v}</text>'
            "</svg>"
        )

    def x_at(i: int) -> float:
        return pad_left + (plot_w * i / (n - 1))

    def y_at(v: int) -> float:
        return baseline_y - (plot_h * v / max_val)

    points = [(x_at(i), y_at(v), d, v) for i, (d, v) in enumerate(series)]

    line_path = "M " + " L ".join(f"{x:.1f},{y:.1f}" for x, y, _, _ in points)
    area_path = line_path + f" L {points[-1][0]:.1f},{baseline_y:.1f} L {points[0][0]:.1f},{baseline_y:.1f} Z"

    gridlines = "".join(
        f'<line x1="{pad_left}" y1="{pad_top + plot_h * step / 4:.1f}" '
        f'x2="{width - pad_right}" y2="{pad_top + plot_h * step / 4:.1f}" '
        f'stroke="{_GRIDLINE}" stroke-width="1" />'
        for step in (1, 2, 3)
    )

    # Per-point hover: a native <title> tooltip on a transparent hit target larger
    # than the visible mark. Simpler than a full crosshair layer, still reachable.
    hover_dots = "".join(
        f'<circle cx="{x:.1f}" cy="{y:.1f}" r="12" fill="transparent">'
        f"<title>{_fmt_date(d)}: {v}</title></circle>"
        for x, y, d, v in points
    )

    last_x, last_y, last_date, last_val = points[-1]
    first_date = points[0][2]
    end_dot = (
        f'<circle cx="{last_x:.1f}" cy="{last_y:.1f}" r="4" fill="{color}" '
        f'stroke="{_SURFACE}" stroke-width="2" />'
    )
    end_label = (
        f'<text x="{last_x:.1f}" y="{max(last_y - 10, 12):.1f}" text-anchor="end" '
        f'font-size="11" fill="{_SECONDARY_INK}">{last_val}</text>'
    )
    axis_labels = (
        f'<text x="{pad_left}" y="{height - 6}" font-size="10" fill="{_MUTED}">{_fmt_date(first_date)}</text>'
        f'<text x="{width - pad_right}" y="{height - 6}" text-anchor="end" font-size="10" '
        f'fill="{_MUTED}">{_fmt_date(last_date)}</text>'
    )

    return (
        f'<svg viewBox="0 0 {width} {height}" width="100%" height="{height}" role="img">'
        f"{gridlines}"
        f'<line x1="{pad_left}" y1="{baseline_y:.1f}" x2="{width - pad_right}" y2="{baseline_y:.1f}" '
        f'stroke="{_BASELINE}" stroke-width="1" />'
        f'<path d="{area_path}" fill="{color}" fill-opacity="0.1" stroke="none" />'
        f'<path d="{line_path}" fill="none" stroke="{color}" stroke-width="2" '
        f'stroke-linejoin="round" stroke-linecap="round" />'
        f"{hover_dots}{end_dot}{end_label}{axis_labels}"
        "</svg>"
    )
