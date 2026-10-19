"""Matplotlib charts shared by the app and the PDF report."""
from __future__ import annotations

from typing import Optional

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt  # noqa: E402

from dcp_core import TestResult  # noqa: E402

C_VIKO = "#2a78d6"     # ViKO method
C_PG = "#eb6834"       # Paige-Green
C_MUTED = "#a3a29c"    # not-used increments
C_INK = "#0b0b0b"
C_INK2 = "#52514e"
C_GRID = "#e4e3df"
C_ZONE = "#2a78d6"

plt.rcParams.update({
    "font.family": "DejaVu Sans",
    "font.size": 8.5,
    "axes.edgecolor": C_GRID,
    "axes.labelcolor": C_INK2,
    "xtick.color": C_INK2,
    "ytick.color": C_INK2,
    "axes.titlesize": 9.5,
    "axes.titleweight": "bold",
    "axes.titlecolor": C_INK,
})


def _style(ax):
    ax.grid(True, color=C_GRID, linewidth=0.6)
    ax.set_axisbelow(True)
    for s in ("top", "right"):
        ax.spines[s].set_visible(False)


def _step(ax, incs, value, color, lw=2.0, label=None, zorder=3, alpha=1.0):
    """Draw a depth-profile step line through the given increments."""
    xs, ys = [], []
    for inc in incs:
        v = value(inc)
        xs += [v, v]
        ys += [inc.top_mm, inc.bottom_mm]
    if xs:
        ax.plot(xs, ys, color=color, lw=lw, label=label, zorder=zorder, alpha=alpha,
                solid_joinstyle="miter")


def _zone(ax, res: TestResult):
    bottom = res.zone_bottom_mm if res.zone_bottom_mm is not None else res.depth_reached_mm
    if bottom > res.zone_top_mm:
        ax.axhspan(res.zone_top_mm, bottom, color=C_ZONE, alpha=0.07, lw=0, zorder=0)
    if res.zone_top_mm > 0:
        ax.axhline(res.zone_top_mm, color=C_INK2, lw=1, ls="--", zorder=1)
    if res.zone_bottom_mm is not None:
        ax.axhline(res.zone_bottom_mm, color=C_INK2, lw=1, ls=":", zorder=1)


def profile_figure(res: TestResult, q_required: Optional[float] = None, figsize=(7.2, 4.2)):
    valid = [i for i in res.increments if i.dn is not None]
    used = [i for i in valid if i.used]
    ymax = max(res.depth_reached_mm, res.zone_bottom_mm or 0, 100) * 1.05

    fig, (a1, a2) = plt.subplots(1, 2, sharey=True, figsize=figsize,
                                 gridspec_kw={"wspace": 0.08})
    for ax in (a1, a2):
        _style(ax)
        _zone(ax, res)
        ax.set_ylim(ymax, 0)

    # --- DN profile
    _step(a1, valid, lambda i: i.dn, C_MUTED, lw=1.2, zorder=2)
    _step(a1, used, lambda i: i.dn, C_INK, lw=2.0)
    a1.set_xlabel("DN (mm/blow)")
    a1.set_ylabel("Depth below test start (mm)")
    a1.set_title("Penetration rate")
    dmax = max([i.dn for i in valid] or [10]) * 1.08
    if res.governing:
        dmax = max(dmax, res.governing.dn * 1.4)
    a1.set_xlim(0, dmax)

    # --- bearing profile
    _step(a2, valid, lambda i: i.q_viko, C_VIKO, lw=1.0, zorder=2, alpha=0.35)
    _step(a2, valid, lambda i: i.q_pg, C_PG, lw=1.0, zorder=2, alpha=0.35)
    _step(a2, used, lambda i: i.q_viko, C_VIKO, lw=2.2, label="ViKO method")
    _step(a2, used, lambda i: i.q_pg, C_PG, lw=2.2, label="Paige-Green")
    if q_required:
        a2.axvline(q_required, color=C_INK, lw=1, ls="--", zorder=1)
        a2.annotate(f"Required\n{q_required:.0f} kPa", (q_required, 0), xytext=(4, -4),
                    textcoords="offset points", color=C_INK2, fontsize=7.5, va="top")
    qs = [v for i in used for v in (i.q_viko, i.q_pg)] or [v for i in valid for v in (i.q_viko, i.q_pg)]
    a2.set_xlim(0, max(qs + [q_required or 0, 50]) * 1.15)
    a2.set_xlabel("Bearing pressure (kPa)")
    a2.set_title("Bearing pressure")

    g = res.governing
    if g:
        ymid = (g.top_mm + g.bottom_mm) / 2
        a1.plot([g.dn], [ymid], "o", ms=7, mfc="white", mec=C_INK, mew=1.6, zorder=5)
        a1.annotate(f"DN {g.dn:.1f}", (g.dn, ymid), xytext=(7, 0), textcoords="offset points",
                    va="center", color=C_INK, fontsize=8, fontweight="bold")
        for q, c, dx, ha in ((g.q_viko, C_VIKO, -8, "right"), (g.q_pg, C_PG, 8, "left")):
            a2.plot([q], [ymid], "o", ms=7, mfc="white", mec=c, mew=1.8, zorder=5)
            a2.annotate(f"{q:.0f}", (q, ymid), xytext=(dx, 0), textcoords="offset points",
                        ha=ha, va="center", color=C_INK, fontsize=8, fontweight="bold",
                        bbox=dict(boxstyle="square,pad=0.1", fc="white", ec="none", alpha=0.8))
    if used:
        a2.legend(loc="upper right", frameon=True, framealpha=0.9, edgecolor="none", fontsize=7.5)

    # key for the zone / grey
    note = ("Shaded band: assessment zone (dashed = founding level, dotted = founding + 2B).  "
            "Faded lines: readings not used.")
    fig.text(0.5, 0.005, note, ha="center", va="bottom", color=C_INK2, fontsize=7)
    fig.subplots_adjust(left=0.1, right=0.98, top=0.92, bottom=0.14)
    return fig


def summary_figure(results: list[TestResult], q_required: Optional[float] = None, figsize=(7.2, None)):
    rs = [r for r in results if r.governing]
    n = max(len(rs), 1)
    h = figsize[1] or (1.1 + 0.42 * n)
    fig, ax = plt.subplots(figsize=(figsize[0], h))
    _style(ax)
    ax.grid(axis="y", visible=False)
    bar_h = 0.36
    names = [r.test.name for r in rs]
    ys = list(range(len(rs)))
    qv = [r.q_viko for r in rs]
    qp = [r.q_pg for r in rs]
    ax.barh([y - bar_h / 2 - 0.01 for y in ys], qv, height=bar_h, color=C_VIKO, label="ViKO method")
    ax.barh([y + bar_h / 2 + 0.01 for y in ys], qp, height=bar_h, color=C_PG, label="Paige-Green")
    for y, a, b in zip(ys, qv, qp):
        ax.text(a, y - bar_h / 2, f" {a:.0f}", va="center", fontsize=7.5, color=C_INK)
        ax.text(b, y + bar_h / 2, f" {b:.0f}", va="center", fontsize=7.5, color=C_INK)
    if q_required:
        ax.axvline(q_required, color=C_INK, lw=1, ls="--")
        ax.text(q_required, -0.75, f" Required {q_required:.0f} kPa", fontsize=7.5, color=C_INK2, va="center")
    ax.set_yticks(ys, names)
    ax.set_ylim(len(rs) - 0.4, -0.95)
    xmax = max(qv + qp + [q_required or 0, 1]) * 1.15
    ax.set_xlim(0, xmax)
    ax.set_xlabel("Bearing pressure at weakest layer in assessment zone (kPa)")
    ax.set_title("Bearing pressure per test position", loc="left", pad=16)
    ax.legend(loc="lower right", frameon=False, fontsize=7.5, ncols=2,
              bbox_to_anchor=(1.0, 1.0), borderaxespad=0)
    fig.tight_layout()
    return fig
