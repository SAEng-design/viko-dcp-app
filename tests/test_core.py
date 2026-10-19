"""Checks the core against the values in ViKO's Excel sheet
(SEP P1-P3 Plant 3 Building Extension, Bases A2, A3, A4a, A4b)."""
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from dcp_core import Reading, TestPosition, analyse, cbr_from_dn, q_viko, cbr_trh  # noqa: E402


def mk(name, zero, readings, founding=0.0, B=None):
    return TestPosition(name=name, zero_reading_mm=zero, founding_depth_mm=founding,
                        footing_width_mm=B, readings=[Reading(5, r) for r in readings])


A2 = mk("Base A2", 0, [120, 240, 370, 500, 610, 700, 755])
A3 = mk("Base A3", 60, [230, 410, 530, 610, 685, 750, 805])
# Excel excluded the first increment by hand; here founding depth does it
A4a = mk("Base A4a", 30, [550, 620, 660, 710, 750], founding=520)
A4b = mk("Base A4b", 35, [455, 630, 695, 745, 790], founding=420)


@pytest.mark.parametrize("dn,cbr", [(3, 110), (10, 22), (24, 7 + 1 / 3), (26, 6 + 2 / 3),
                                    (35, 4.5), (36, 4 + 1 / 3), (70, 1.5), (80, 1), (200, 1)])
def test_table(dn, cbr):
    assert cbr_from_dn(dn) == pytest.approx(cbr, rel=1e-9)


def test_table_vs_trh():
    for dn in range(3, 61):
        assert cbr_from_dn(dn) == pytest.approx(cbr_trh(dn), rel=0.13)


@pytest.mark.parametrize("test,cbr,kpa", [
    (A2, 6.666667, 92.196),
    (A3, 4.333333, 69.261),
    (A4a, 15.0, 157.966),
    (A4b, 4.5, 71.018),
])
def test_matches_excel(test, cbr, kpa):
    r = analyse(test)
    assert r.cbr == pytest.approx(cbr, rel=1e-5)
    assert r.q_viko == pytest.approx(kpa, rel=1e-4)


def test_founding_excludes_and_zone():
    t = mk("x", 0, [100, 200, 300, 400, 500], founding=200, B=100)  # zone 200-400
    r = analyse(t)
    assert [i.status for i in r.increments] == ["Above founding", "Above founding", "Used", "Used", "Below zone"]
    assert r.depth_ok is True


def test_manual_exclude_and_short_test():
    t = mk("x", 0, [300, 350, 400], founding=0, B=600)
    t.readings[0].exclude = True
    t.readings[0].note = "Loose backfill"
    r = analyse(t)
    assert r.governing.no == 2 and r.depth_ok is False
    assert any("not assessed" in w for w in r.warnings)


def test_invalid_reading_ignored():
    t = mk("x", 0, [100, 100, 200])
    r = analyse(t)
    assert r.increments[1].status == "Invalid"
    assert r.increments[2].pen_mm == 100


def test_q_viko_formula():
    assert q_viko(10) == pytest.approx(26.16 * 10 ** 0.664)
