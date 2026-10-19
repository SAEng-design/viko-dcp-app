"""
ViKO DCP Test — on-site data capture and bearing pressure report.

Run locally:   streamlit run app.py
"""
from __future__ import annotations

import json
import uuid
from datetime import date
from pathlib import Path

import matplotlib.pyplot as plt
import pandas as pd
import streamlit as st

from dcp_charts import profile_figure, summary_figure
from dcp_core import DN_MIN, Reading, TestPosition, analyse, findings_text
from dcp_report import build_pdf

APP_DIR = Path(__file__).parent
LOGO = APP_DIR / "viko_logo.png"
TEST_LEVELS = ["Excavation base", "Natural ground level", "Other"]
DEFAULT_ROW = {"blows": 5, "reading_mm": None, "exclude": False, "note": ""}

st.set_page_config(page_title="ViKO DCP Test", page_icon="🔩", layout="wide")
st.markdown("""
<style>
.dcp-grid {display:grid; grid-template-columns:repeat(4, minmax(0,1fr)); gap:8px; margin:4px 0 12px;}
@media (max-width: 700px) {.dcp-grid {grid-template-columns:repeat(2, minmax(0,1fr));}}
.dcp-card {background:#eef3fa; border-radius:8px; padding:8px 10px;}
.dcp-l {font-size:0.78rem; color:#55544f;}
.dcp-v {font-size:1.45rem; font-weight:600; color:#1b1b1b; line-height:1.3;}
.dcp-s {font-size:0.75rem; color:#55544f; min-height:1em;}
</style>""", unsafe_allow_html=True)


# =====================================================================  state
def _new_test(name: str) -> dict:
    return {"id": uuid.uuid4().hex[:8], "name": name, "description": "", "test_level": TEST_LEVELS[0],
            "zero_reading_mm": 0.0, "founding_depth_mm": 0.0, "footing_width_mm": 0.0,
            "refusal": False, "remarks": "", "readings": [], "ver": 0}


def _init():
    ss = st.session_state
    if "tests" in ss:
        return
    ss.gen = 0
    ss.project = {"project": "", "job_no": "", "client": "", "site": "", "tested_by": "",
                  "report_by": "", "test_date": date.today().isoformat(), "conditions": "",
                  "general_remarks": "", "q_required": 0.0}
    ss.tests = [_new_test("TP-1")]
    ss.active = ss.tests[0]["id"]
    ss.pdf = None
    ss.flash = None


_init()
ss = st.session_state


def _k(name: str, tid: str = "") -> str:
    """Widget key; includes a generation counter so loading a file refreshes all widgets."""
    return f"g{ss.gen}_{name}_{tid}"


def _editor_key(t: dict) -> str:
    return _k(f"ed{t['ver']}", t["id"])


def _apply_delta(rows: list[dict], delta: dict | None) -> list[dict]:
    """Apply a st.data_editor delta (edited/deleted/added rows) to the base rows."""
    rows = [dict(r) for r in rows]
    if not delta:
        return rows
    for idx, change in delta.get("edited_rows", {}).items():
        i = int(idx)
        if i < len(rows):
            rows[i].update(change)
    deleted = {int(i) for i in delta.get("deleted_rows", [])}
    rows = [r for i, r in enumerate(rows) if i not in deleted]
    for a in delta.get("added_rows", []):
        rows.append({**DEFAULT_ROW, **a})
    return rows


def current_rows(t: dict) -> list[dict]:
    return _apply_delta(t["readings"], ss.get(_editor_key(t)))


def _commit(t: dict, rows: list[dict]):
    t["readings"] = rows
    t["ver"] += 1           # new editor key -> editor starts clean from the committed rows


def get_test(tid: str) -> dict:
    return next(t for t in ss.tests if t["id"] == tid)


def to_position(t: dict, rows: list[dict] | None = None) -> TestPosition:
    rows = current_rows(t) if rows is None else rows
    rd = []
    for r in rows:
        if r.get("reading_mm") is None or pd.isna(r.get("reading_mm")):
            continue
        blows = r.get("blows")
        blows = 0 if blows is None or pd.isna(blows) else int(blows)
        rd.append(Reading(blows, float(r["reading_mm"]), bool(r.get("exclude") or False), str(r.get("note") or "")))
    B = float(t.get("footing_width_mm") or 0)
    return TestPosition(name=t["name"] or "Unnamed", zero_reading_mm=float(t["zero_reading_mm"] or 0),
                        founding_depth_mm=float(t["founding_depth_mm"] or 0),
                        footing_width_mm=B if B > 0 else None, test_level=t["test_level"],
                        description=t.get("description", ""), refusal=bool(t["refusal"]),
                        remarks=t.get("remarks", ""), readings=rd)


def export_state() -> dict:
    tests = []
    for t in ss.tests:
        d = {k: v for k, v in t.items() if k not in ("ver",)}
        d["readings"] = [{k: (None if (isinstance(v, float) and pd.isna(v)) else v) for k, v in r.items()}
                         for r in current_rows(t)]
        tests.append(d)
    return {"app": "viko-dcp", "version": 1, "project": ss.project, "tests": tests}


def import_state(data: dict):
    ss.gen += 1
    ss.project = {**ss.project, **data.get("project", {})}
    ss.tests = []
    for d in data.get("tests", []):
        t = _new_test(d.get("name", "TP"))
        for k in t:
            if k in d and k not in ("id", "ver"):
                t[k] = d[k]
        t["readings"] = [{**DEFAULT_ROW, **r} for r in t["readings"]]
        ss.tests.append(t)
    if not ss.tests:
        ss.tests = [_new_test("TP-1")]
    ss.active = ss.tests[0]["id"]
    ss.pdf = None


# =====================================================================  callbacks
def cb_add_reading(tid: str):
    t = get_test(tid)
    blows = ss.get(_k("qa_blows", tid))
    reading = ss.get(_k("qa_reading", tid))
    if reading is None:
        ss.flash = ("warning", "Enter the rule reading first.")
        return
    rows = current_rows(t)
    valid = [r for r in rows if r.get("reading_mm") is not None and not pd.isna(r.get("reading_mm"))]
    prev = float(valid[-1]["reading_mm"]) if valid else float(t["zero_reading_mm"] or 0)
    if reading <= prev:
        ss.flash = ("error", f"Reading {reading:.0f} mm is not deeper than the previous reading ({prev:.0f} mm). "
                             "Not added — check the rule.")
        return
    rows.append({**DEFAULT_ROW, "blows": int(blows or 5), "reading_mm": float(reading)})
    _commit(t, rows)
    ss[_k("qa_reading", tid)] = None
    ss.flash = None


def cb_new_test():
    n = len(ss.tests) + 1
    names = {t["name"] for t in ss.tests}
    while f"TP-{n}" in names:
        n += 1
    t = _new_test(f"TP-{n}")
    ss.tests.append(t)
    ss.active = t["id"]
    ss.pdf = None


def cb_delete_test(tid: str):
    ss.tests = [t for t in ss.tests if t["id"] != tid] or [_new_test("TP-1")]
    ss.active = ss.tests[0]["id"]
    ss.pdf = None


def cb_undo_last(tid: str):
    t = get_test(tid)
    rows = current_rows(t)
    if rows:
        _commit(t, rows[:-1])


# =====================================================================  sidebar
with st.sidebar:
    if LOGO.exists():
        st.image(str(LOGO), width=170)
    st.header("Project")
    p = ss.project
    p["project"] = st.text_input("Project", p["project"], key=_k("p_project"))
    p["job_no"] = st.text_input("Job no.", p["job_no"], key=_k("p_job"))
    p["client"] = st.text_input("Client", p["client"], key=_k("p_client"))
    p["site"] = st.text_input("Site / location", p["site"], key=_k("p_site"))
    p["tested_by"] = st.text_input("Tested by", p["tested_by"], key=_k("p_tested"))
    p["report_by"] = st.text_input("Report by", p["report_by"], key=_k("p_report"))
    try:
        td = date.fromisoformat(p["test_date"])
    except (TypeError, ValueError):
        td = date.today()
    p["test_date"] = st.date_input("Test date", td, key=_k("p_date")).isoformat()
    p["conditions"] = st.text_input("Weather / conditions", p["conditions"], key=_k("p_cond"))
    p["q_required"] = st.number_input("Required bearing pressure (kPa, 0 = not checked)", min_value=0.0,
                                      value=float(p.get("q_required") or 0), step=25.0, key=_k("p_qreq"))

    st.header("Save / load")
    st.caption("Download a backup regularly on site — if the page reloads, unsaved data is lost.")
    save_slot = st.empty()       # filled at the end of the script, so it holds the latest data
    up = st.file_uploader("Load a saved test file (.json)", type=["json"], key=_k("upload"))
    if up is not None and st.button("Load file", type="primary", key=_k("loadbtn")):
        try:
            import_state(json.loads(up.getvalue().decode("utf-8")))
            st.rerun()
        except Exception as e:  # noqa: BLE001
            st.error(f"Could not read file: {e}")

q_req = float(ss.project.get("q_required") or 0) or None

# =====================================================================  main
st.title("DCP Test — Bearing Pressure")
st.caption("ViKO Consulting Engineers  |  DN → CBR (ViKO Table 1)  |  Bearing: ViKO method & Paige-Green (2009)")

tab_site, tab_sum = st.tabs(["📍 Site entry", "📄 Summary & report"])

# ---------------------------------------------------------------- site entry
with tab_site:
    c1, c2, c3 = st.columns([3, 1, 1], vertical_alignment="bottom")
    ids = [t["id"] for t in ss.tests]
    if ss.active not in ids:
        ss.active = ids[0]
    labels = {t["id"]: t["name"] or "Unnamed" for t in ss.tests}
    ss.active = c1.selectbox("Test position", ids, index=ids.index(ss.active),
                             format_func=lambda i: labels[i], key=_k(f"sel{len(ids)}_{ss.active}"))
    c2.button("➕ New test", on_click=cb_new_test, width="stretch")
    t = get_test(ss.active)
    tid = t["id"]
    with c3.popover("🗑 Delete", width="stretch"):
        st.write(f"Delete **{t['name']}** and all its readings?")
        st.button("Yes, delete", type="primary", on_click=cb_delete_test, args=(tid,), key=_k("del", tid))

    has_readings = len(t["readings"]) > 0
    with st.expander("Test setup", expanded=not has_readings):
        a, b = st.columns(2)
        t["name"] = a.text_input("Test name", t["name"], key=_k("name", tid))
        t["description"] = b.text_input("Description / position", t["description"], key=_k("desc", tid),
                                        placeholder="e.g. Base A3, NE corner")
        t["test_level"] = st.radio("Test starts from", TEST_LEVELS, index=TEST_LEVELS.index(t["test_level"]),
                                   horizontal=True, key=_k("lvl", tid))
        a, b, c = st.columns(3)
        t["zero_reading_mm"] = a.number_input("Zero reading on rule (mm)", value=float(t["zero_reading_mm"]),
                                              step=5.0, format="%.0f", key=_k("zero", tid))
        t["founding_depth_mm"] = b.number_input(
            "Founding depth below test start (mm)", min_value=0.0, value=float(t["founding_depth_mm"]),
            step=50.0, format="%.0f", key=_k("found", tid),
            help="0 if the test starts at founding level. Readings above this depth are not assessed.")
        t["footing_width_mm"] = c.number_input(
            "Footing width B (mm, 0 = not given)", min_value=0.0, value=float(t["footing_width_mm"] or 0),
            step=50.0, format="%.0f", key=_k("B", tid),
            help="Assessment zone = founding depth to founding depth + 2B.")
        t["remarks"] = st.text_area("Remarks (soil description, water, etc.)", t["remarks"], height=70,
                                    key=_k("rem", tid))

    # ---- quick entry
    rows = current_rows(t)
    last_blows = int(rows[-1]["blows"]) if rows and rows[-1].get("blows") else 5
    st.subheader("Add reading")
    with st.form(_k("qa_form", tid), border=True):
        a, b, c = st.columns([1, 1.4, 1], vertical_alignment="bottom")
        a.number_input("Blows", min_value=1, max_value=50, value=last_blows, step=1, key=_k("qa_blows", tid))
        rk = _k("qa_reading", tid)
        b.number_input("Rule reading (mm)", min_value=0.0, step=5.0, format="%.0f", key=rk,
                       placeholder="e.g. 455", **({} if rk in ss else {"value": None}))
        c.form_submit_button("Add ✚", type="primary", width="stretch",
                             on_click=cb_add_reading, args=(tid,))
    if ss.flash:
        kind, msg = ss.flash
        getattr(st, kind)(msg)
        ss.flash = None

    a, b = st.columns([1, 1])
    a.button("↶ Undo last reading", on_click=cb_undo_last, args=(tid,), disabled=not rows, key=_k("undo", tid))
    t["refusal"] = b.checkbox("DCP refusal reached", t["refusal"], key=_k("ref", tid))

    # ---- live result
    res = analyse(to_position(t, rows))
    valid_incs = [i for i in res.increments if i.dn is not None]
    if valid_incs:
        li = valid_incs[-1]
        cbr_txt = "≥110" if li.dn < DN_MIN else f"{li.cbr:.1f}"
        st.info(f"**Last reading ({li.top_mm:.0f}–{li.bottom_mm:.0f} mm):** DN {li.dn:.1f} mm/blow · "
                f"CBR {cbr_txt} % · ViKO {li.q_viko:.0f} kPa · P-G {li.q_pg:.0f} kPa  — *{li.status}*")
    def _card(label, value, sub=""):
        return (f'<div class="dcp-card"><div class="dcp-l">{label}</div><div class="dcp-v">{value}</div>'
                f'<div class="dcp-s">{sub}</div></div>')

    def _vs(q):
        if not (q_req and res.governing):
            return ""
        ok = q >= q_req
        return f'<span style="color:{"#1d7a3a" if ok else "#b3261e"}">{"✔" if ok else "✘"} {q - q_req:+.0f} vs {q_req:.0f}</span>'

    need = f"need {res.zone_bottom_mm:.0f} mm" if res.zone_bottom_mm else "below test start"
    st.markdown(
        '<div class="dcp-grid">'
        + _card("Depth reached", f"{res.depth_reached_mm:.0f} mm", need)
        + _card("Lowest CBR in zone", f"{res.cbr:.1f} %" if res.governing else "–",
                f"DN {res.governing.dn:.1f} mm/blow" if res.governing else "")
        + _card("ViKO method", f"{res.q_viko:.0f} kPa" if res.governing else "–", _vs(res.q_viko or 0))
        + _card("Paige-Green", f"{res.q_pg:.0f} kPa" if res.governing else "–", _vs(res.q_pg or 0))
        + "</div>", unsafe_allow_html=True)
    if res.depth_ok is False:
        st.warning(f"Keep going: founding + 2B = {res.zone_bottom_mm:.0f} mm, test is at "
                   f"{res.depth_reached_mm:.0f} mm.")
    elif res.depth_ok:
        st.success("Test depth covers founding + 2B.")

    # ---- readings editor + calculated table
    st.subheader("Readings")
    st.caption("Edit any cell to correct a reading. Tick **Exclude** and give a reason to leave a reading out "
               "of the assessment — the reason is printed on the report.")
    edit_col, calc_col = st.columns([1, 1.35])
    with edit_col:
        st.data_editor(
            pd.DataFrame(t["readings"] or [], columns=list(DEFAULT_ROW)),
            key=_editor_key(t), num_rows="dynamic", hide_index=True, width="stretch",
            column_config={
                "blows": st.column_config.NumberColumn("Blows", min_value=1, step=1, default=5, width="small"),
                "reading_mm": st.column_config.NumberColumn("Reading (mm)", step=1, format="%.0f"),
                "exclude": st.column_config.CheckboxColumn("Exclude", default=False, width="small"),
                "note": st.column_config.TextColumn("Reason / note"),
            },
        )
    with calc_col:
        if res.increments:
            df = pd.DataFrame([{
                "No": i.no, "Depth (mm)": f"{i.top_mm:.0f}–{i.bottom_mm:.0f}",
                "DN": None if i.dn is None else round(i.dn, 1),
                "CBR": None if i.cbr is None else ("≥110" if i.dn < DN_MIN else f"{i.cbr:.1f}"),
                "ViKO kPa": None if i.q_viko is None else round(i.q_viko),
                "P-G kPa": None if i.q_pg is None else round(i.q_pg),
                "Status": ("★ Governing" if res.governing and i.no == res.governing.no else i.status),
            } for i in res.increments])
            st.dataframe(df, hide_index=True, width="stretch")
        else:
            st.caption("Calculated values appear here once readings are added.")

    if valid_incs:
        fig = profile_figure(res, q_req)
        st.pyplot(fig, width="stretch")
        plt.close(fig)
        with st.expander("Findings for this test", expanded=False):
            for f in findings_text(res, q_req):
                st.markdown(f"- {f}")

# ---------------------------------------------------------------- summary & report
with tab_sum:
    results = [analyse(to_position(x)) for x in ss.tests]
    st.subheader("Summary")
    sdf = pd.DataFrame([{
        "Test": r.test.name, "Start level": r.test.test_level,
        "Founding (mm)": round(r.zone_top_mm), "B (mm)": round(r.test.footing_width_mm) if r.test.footing_width_mm else None,
        "Depth reached (mm)": round(r.depth_reached_mm),
        "Depth OK": {True: "✅", False: "⚠️ short", None: "–"}[r.depth_ok],
        "Weakest layer (mm)": f"{r.governing.top_mm:.0f}–{r.governing.bottom_mm:.0f}" if r.governing else "–",
        "DN": round(r.governing.dn, 1) if r.governing else None,
        "CBR": round(r.cbr, 1) if r.governing else None,
        "ViKO (kPa)": round(r.q_viko) if r.governing else None,
        "Paige-Green (kPa)": round(r.q_pg) if r.governing else None,
    } for r in results])
    st.dataframe(sdf, hide_index=True, width="stretch")
    if any(r.governing for r in results):
        fig = summary_figure(results, q_req)
        st.pyplot(fig, width="stretch")
        plt.close(fig)
        rs = [r for r in results if r.governing]
        gv, gp = min(rs, key=lambda r: r.q_viko), min(rs, key=lambda r: r.q_pg)
        a, b = st.columns(2)
        a.metric(f"Lowest — ViKO method ({gv.test.name})", f"{gv.q_viko:.0f} kPa")
        b.metric(f"Lowest — Paige-Green ({gp.test.name})", f"{gp.q_pg:.0f} kPa")

    ss.project["general_remarks"] = st.text_area(
        "General remarks for the report", ss.project.get("general_remarks", ""), height=100,
        key=_k("p_general"), placeholder="e.g. Founding material: moist, reddish-brown silty sand …")

    st.subheader("PDF report")
    if st.button("Generate PDF report", type="primary"):
        with st.spinner("Building report…"):
            ss.pdf = build_pdf(ss.project, results, q_req, str(LOGO) if LOGO.exists() else None)
    if ss.pdf:
        fname = f"DCP_Report_{(ss.project.get('job_no') or 'job').replace(' ', '_')}_{ss.project['test_date']}.pdf"
        st.download_button("⬇ Download PDF", ss.pdf, file_name=fname, mime="application/pdf")
        st.caption("Regenerate after any change — the PDF is a snapshot.")

# ---------------------------------------------------------------- save (last, so it holds the latest data)
with save_slot:
    job = (ss.project.get("job_no") or "job").replace(" ", "_")
    st.download_button("💾 Download backup (.json)", json.dumps(export_state(), indent=1, default=str),
                       file_name=f"DCP_{job}_{ss.project['test_date']}.json", mime="application/json",
                       width="stretch")
