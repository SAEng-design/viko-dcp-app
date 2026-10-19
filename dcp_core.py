"""
DCP calculation core - no Streamlit code in here, so it can be unit-tested
and reused (e.g. in a Jupyter calc sheet).

Method
------
1. Penetration rate  DN = (reading_i - reading_{i-1}) / blows_i      [mm/blow]
2. In-situ CBR from DN using the ViKO Table 1 (DCP number vs in-situ CBR),
   interpolated linearly between table points. The table agrees with the
   Transvaal Roads Department correlation CBR = 410 * DN^-1.27 within ~5 %
   for DN 3-60.
3. Bearing pressure, two methods reported side by side:
     ViKO house method :  q = 26.16 * CBR^0.664              [kPa]  (origin unknown)
     Paige-Green (2009):  q = 3426.8 * DN^-1.0101            [kPa]
4. Only increments inside the assessment zone are considered:
     zone top    = founding depth below test start level
     zone bottom = founding depth + 2B (if footing width B is given),
                   otherwise the bottom of the test
   Increments that overlap the zone are used (conservative). The engineer can
   exclude further increments manually, with a reason that is reported.
5. The governing value is the weakest used increment (largest DN / lowest CBR).
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Optional

import numpy as np

# ---------------------------------------------------------------- correlations
# ViKO Table 1: DCP number (mm/blow) -> in-situ CBR (%)
VIKO_TABLE: list[tuple[float, float]] = [
    (3, 110), (4, 75), (5, 55), (6, 45), (7, 35), (8, 30), (9, 25), (10, 22),
    (11, 20), (12, 18), (13, 16), (14, 15), (15, 14), (16, 13), (17, 12),
    (18, 11), (19, 10), (20, 9), (22, 8), (25, 7), (28, 6), (32, 5), (38, 4),
    (48, 3), (60, 2), (80, 1),
]
_DN = np.array([p[0] for p in VIKO_TABLE], dtype=float)
_CBR = np.array([p[1] for p in VIKO_TABLE], dtype=float)

DN_MIN = 3.0    # below this the table gives ">110"
DN_MAX = 80.0   # above this the table gives CBR 1 (lower bound of the table)

VIKO_A, VIKO_B = 26.16, 0.664          # q = A * CBR^B
PG_A, PG_B = 3426.8, -1.0101           # q = A * DN^B  (Paige-Green 2009)


def cbr_from_dn(dn: float) -> float:
    """In-situ CBR (%) from DN (mm/blow), ViKO Table 1 with linear interpolation.
    Clipped to the table range: DN < 3 -> 110 (reported as >=110), DN > 80 -> 1."""
    dn = float(np.clip(dn, DN_MIN, DN_MAX))
    return float(np.interp(dn, _DN, _CBR))


def cbr_trh(dn: float) -> float:
    """Transvaal Roads Dept correlation, CBR = 410 DN^-1.27 (reference only)."""
    return 410.0 * max(dn, 2.0) ** -1.27


def q_viko(cbr: float) -> float:
    """ViKO house method bearing pressure (kPa) from CBR."""
    return VIKO_A * max(cbr, 0.0) ** VIKO_B


def q_paige_green(dn: float) -> float:
    """Paige-Green (2009) bearing pressure (kPa) from DN. DN clipped to >= 3."""
    return PG_A * max(dn, DN_MIN) ** PG_B


# ---------------------------------------------------------------- data model
@dataclass
class Reading:
    blows: int
    reading_mm: float
    exclude: bool = False
    note: str = ""


@dataclass
class TestPosition:
    name: str
    zero_reading_mm: float = 0.0
    founding_depth_mm: float = 0.0          # below test start level
    footing_width_mm: Optional[float] = None
    test_level: str = "Excavation base"
    description: str = ""
    refusal: bool = False
    remarks: str = ""
    readings: list[Reading] = field(default_factory=list)


@dataclass
class Increment:
    no: int
    blows: int
    reading_mm: float
    pen_mm: float
    top_mm: float
    bottom_mm: float
    dn: Optional[float]
    cbr: Optional[float]
    q_viko: Optional[float]
    q_pg: Optional[float]
    status: str          # "Used" | "Above founding" | "Below zone" | "Excluded" | "Invalid"
    note: str = ""

    @property
    def used(self) -> bool:
        return self.status == "Used"


@dataclass
class TestResult:
    test: TestPosition
    increments: list[Increment]
    zone_top_mm: float
    zone_bottom_mm: Optional[float]       # None -> to bottom of test
    required_depth_mm: Optional[float]    # founding + 2B
    depth_reached_mm: float
    depth_ok: Optional[bool]              # None if B not given
    governing: Optional[Increment]
    avg_dn: Optional[float]               # thickness-weighted DN over used increments
    warnings: list[str]

    # convenience
    @property
    def q_viko(self) -> Optional[float]:
        return self.governing.q_viko if self.governing else None

    @property
    def q_pg(self) -> Optional[float]:
        return self.governing.q_pg if self.governing else None

    @property
    def cbr(self) -> Optional[float]:
        return self.governing.cbr if self.governing else None


# ---------------------------------------------------------------- analysis
def analyse(test: TestPosition) -> TestResult:
    warnings: list[str] = []
    zone_top = max(float(test.founding_depth_mm or 0.0), 0.0)
    B = float(test.footing_width_mm) if test.footing_width_mm else None
    zone_bot = zone_top + 2.0 * B if B else None

    incs: list[Increment] = []
    prev = float(test.zero_reading_mm)
    for i, r in enumerate(test.readings, start=1):
        blows = int(r.blows or 0)
        reading = float(r.reading_mm)
        pen = reading - prev
        top = prev - test.zero_reading_mm
        bot = reading - test.zero_reading_mm
        note = (r.note or "").strip()

        if blows <= 0 or pen <= 0:
            status = "Invalid"
            dn = cbr = qv = qp = None
            note = note or ("No blows recorded" if blows <= 0 else "Reading not deeper than previous")
        else:
            dn = pen / blows
            cbr = cbr_from_dn(dn)
            qv = q_viko(cbr)
            qp = q_paige_green(dn)
            if r.exclude:
                status = "Excluded"
                if not note:
                    note = "Excluded by engineer (no reason given)"
            elif bot <= zone_top:
                status = "Above founding"
            elif zone_bot is not None and top >= zone_bot:
                status = "Below zone"
            else:
                status = "Used"
        incs.append(Increment(i, blows, reading, pen, top, bot, dn, cbr, qv, qp, status, note))
        if pen > 0:
            prev = reading

    depth_reached = max([inc.bottom_mm for inc in incs], default=0.0)
    used = [inc for inc in incs if inc.used]
    governing = max(used, key=lambda x: x.dn) if used else None
    avg_dn = (sum(i.pen_mm for i in used) / sum(i.blows for i in used)) if used else None

    depth_ok = None
    if zone_bot is not None:
        depth_ok = depth_reached >= zone_bot
        if not depth_ok:
            warnings.append(
                f"Test reached {depth_reached:.0f} mm; the influence zone (founding + 2B) "
                f"extends to {zone_bot:.0f} mm. Ground below {depth_reached:.0f} mm is not assessed."
            )
    if depth_reached <= zone_top and incs:
        warnings.append("Test did not penetrate below the founding depth - no readings to assess.")
    if any(i.status == "Invalid" for i in incs):
        warnings.append("One or more readings are invalid (zero blows or no penetration) and were ignored.")
    if governing and governing.dn > DN_MAX:
        warnings.append(f"Governing DN {governing.dn:.0f} mm/blow is beyond the table (CBR < 1); CBR taken as 1.")

    return TestResult(test, incs, zone_top, zone_bot, zone_bot, depth_reached,
                      depth_ok, governing, avg_dn, warnings)


def findings_text(res: TestResult, q_required: Optional[float] = None) -> list[str]:
    """Plain-language findings for the report."""
    t = res.test
    out: list[str] = []
    out.append(
        f"Test started at {t.test_level.lower()} and reached {res.depth_reached_mm:.0f} mm"
        + (" (refusal)." if t.refusal else ".")
    )
    if res.zone_bottom_mm is not None:
        out.append(
            f"Founding level {res.zone_top_mm:.0f} mm below test start; footing width B = "
            f"{t.footing_width_mm:.0f} mm, so the assessment zone is {res.zone_top_mm:.0f}–"
            f"{res.zone_bottom_mm:.0f} mm (founding + 2B)."
        )
    else:
        out.append(
            f"Founding level {res.zone_top_mm:.0f} mm below test start; no footing width given, so "
            f"all readings below founding level were assessed."
        )
    g = res.governing
    if g is None:
        out.append("No valid readings within the assessment zone - no bearing pressure can be derived.")
    else:
        cbr_txt = "≥110" if g.dn < DN_MIN else f"{g.cbr:.1f}"
        out.append(
            f"Weakest layer at {g.top_mm:.0f}–{g.bottom_mm:.0f} mm: DN = {g.dn:.1f} mm/blow, "
            f"CBR ≈ {cbr_txt} %. Bearing pressure: ViKO method {g.q_viko:.0f} kPa; "
            f"Paige-Green {g.q_pg:.0f} kPa."
        )
        if q_required:
            for label, q in (("ViKO method", g.q_viko), ("Paige-Green", g.q_pg)):
                verdict = "meets" if q >= q_required else "does NOT meet"
                out.append(f"{label} {verdict} the required {q_required:.0f} kPa.")
    excl = [i for i in res.increments if i.status == "Excluded"]
    for i in excl:
        out.append(f"Reading {i.no} ({i.top_mm:.0f}–{i.bottom_mm:.0f} mm) excluded: {i.note}")
    out.extend(res.warnings)
    if t.remarks.strip():
        out.append(f"Engineer's remarks: {t.remarks.strip()}")
    return out
