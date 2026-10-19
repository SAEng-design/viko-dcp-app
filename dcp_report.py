"""PDF report for the DCP app (ReportLab)."""
from __future__ import annotations

import io
import os
from datetime import date, datetime
from typing import Optional

import matplotlib
import matplotlib.pyplot as plt
from reportlab.lib import colors
from reportlab.lib.enums import TA_LEFT
from reportlab.lib.pagesizes import A4
from reportlab.lib.styles import ParagraphStyle
from reportlab.lib.units import mm
from reportlab.pdfbase import pdfmetrics
from reportlab.pdfbase.ttfonts import TTFont
from reportlab.pdfgen import canvas as rl_canvas
from reportlab.platypus import (Image, KeepTogether, PageBreak, Paragraph, SimpleDocTemplate,
                                Spacer, Table, TableStyle)

from dcp_charts import profile_figure, summary_figure
from dcp_core import DN_MIN, PG_A, PG_B, VIKO_A, VIKO_B, TestResult, findings_text

# ------------------------------------------------------------------ fonts & styles
_FONT_DIR = os.path.join(matplotlib.get_data_path(), "fonts", "ttf")
pdfmetrics.registerFont(TTFont("DejaVu", os.path.join(_FONT_DIR, "DejaVuSans.ttf")))
pdfmetrics.registerFont(TTFont("DejaVu-Bold", os.path.join(_FONT_DIR, "DejaVuSans-Bold.ttf")))
pdfmetrics.registerFontFamily("DejaVu", normal="DejaVu", bold="DejaVu-Bold")

BLUE = colors.HexColor("#3f6fb5")
BLUE_LIGHT = colors.HexColor("#dfe8f5")
BLUE_PALE = colors.HexColor("#f3f6fb")
INK = colors.HexColor("#1b1b1b")
INK2 = colors.HexColor("#55544f")
RULE = colors.HexColor("#c9d5e8")
GOOD = colors.HexColor("#1d7a3a")
BAD = colors.HexColor("#b3261e")

S = {
    "h1": ParagraphStyle("h1", fontName="DejaVu-Bold", fontSize=13, leading=16, textColor=BLUE, spaceAfter=4),
    "h2": ParagraphStyle("h2", fontName="DejaVu-Bold", fontSize=10.5, leading=13, textColor=BLUE,
                         spaceBefore=8, spaceAfter=4),
    "body": ParagraphStyle("body", fontName="DejaVu", fontSize=8.5, leading=11.5, textColor=INK, alignment=TA_LEFT),
    "small": ParagraphStyle("small", fontName="DejaVu", fontSize=7.3, leading=9.5, textColor=INK2),
    "cell": ParagraphStyle("cell", fontName="DejaVu", fontSize=7.3, leading=9, textColor=INK),
    "cellb": ParagraphStyle("cellb", fontName="DejaVu-Bold", fontSize=7.3, leading=9, textColor=INK),
    "bullet": ParagraphStyle("bullet", fontName="DejaVu", fontSize=8.5, leading=11.5, textColor=INK,
                             leftIndent=10, bulletIndent=0, spaceAfter=2),
}

PAGE_W, PAGE_H = A4
MARGIN = 15 * mm
CONTENT_W = PAGE_W - 2 * MARGIN


def _p(text, style="body"):
    return Paragraph(text, S[style])


def _fig_image(fig, width_mm):
    buf = io.BytesIO()
    fig.savefig(buf, format="png", dpi=200, bbox_inches="tight")
    plt.close(fig)
    buf.seek(0)
    img = Image(buf)
    ratio = img.imageHeight / img.imageWidth
    img.drawWidth = width_mm * mm
    img.drawHeight = width_mm * mm * ratio
    return img


def _grid_table(data, col_widths, header_rows=1, zebra=True, extra=None):
    t = Table(data, colWidths=col_widths, repeatRows=header_rows)
    style = [
        ("FONT", (0, 0), (-1, -1), "DejaVu", 7.3),
        ("FONT", (0, 0), (-1, header_rows - 1), "DejaVu-Bold", 7.3),
        ("BACKGROUND", (0, 0), (-1, header_rows - 1), BLUE_LIGHT),
        ("TEXTCOLOR", (0, 0), (-1, -1), INK),
        ("LINEBELOW", (0, header_rows - 1), (-1, header_rows - 1), 0.8, BLUE),
        ("LINEBELOW", (0, header_rows), (-1, -1), 0.25, RULE),
        ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
        ("TOPPADDING", (0, 0), (-1, -1), 2.2),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 2.2),
        ("LEFTPADDING", (0, 0), (-1, -1), 3),
        ("RIGHTPADDING", (0, 0), (-1, -1), 3),
    ]
    if zebra:
        for r in range(header_rows, len(data)):
            if (r - header_rows) % 2 == 1:
                style.append(("BACKGROUND", (0, r), (-1, r), BLUE_PALE))
    if extra:
        style += extra
    t.setStyle(TableStyle(style))
    return t


def _kv_table(pairs, cols=2):
    """Key/value pairs laid out in `cols` column pairs."""
    rows = []
    per_row = cols
    for i in range(0, len(pairs), per_row):
        row = []
        for k, v in pairs[i:i + per_row]:
            row += [_p(f"<b>{k}</b>", "cell"), _p(str(v) if v not in (None, "") else "–", "cell")]
        while len(row) < 2 * per_row:
            row += ["", ""]
        rows.append(row)
    kw = 30 * mm
    vw = (CONTENT_W - cols * kw) / cols
    t = Table(rows, colWidths=[kw, vw] * cols)
    t.setStyle(TableStyle([
        ("VALIGN", (0, 0), (-1, -1), "TOP"),
        ("LINEBELOW", (0, 0), (-1, -1), 0.25, RULE),
        ("TOPPADDING", (0, 0), (-1, -1), 2.2),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 2.2),
        ("LEFTPADDING", (0, 0), (-1, -1), 3),
    ]))
    return t


def _fmt(v, nd=0, dash="–"):
    if v is None:
        return dash
    return f"{v:,.{nd}f}".replace(",", " ")


# ------------------------------------------------------------------ page decoration
class _NumberedCanvas(rl_canvas.Canvas):
    def __init__(self, *a, **k):
        super().__init__(*a, **k)
        self._saved = []

    def showPage(self):
        self._saved.append(dict(self.__dict__))
        self._startPage()

    def save(self):
        n = len(self._saved)
        for st in self._saved:
            self.__dict__.update(st)
            self.setFont("DejaVu", 7)
            self.setFillColor(INK2)
            self.drawRightString(PAGE_W - MARGIN, 9 * mm, f"Page {self._pageNumber} of {n}")
            super().showPage()
        super().save()


def _decorate(project: dict, logo_path: Optional[str]):
    def on_page(c, doc):
        c.saveState()
        top = PAGE_H - 10 * mm
        logo_h = 15 * mm
        if logo_path and os.path.exists(logo_path):
            c.drawImage(logo_path, MARGIN, top - logo_h, width=logo_h * 1138 / 581, height=logo_h,
                        preserveAspectRatio=True, mask="auto")
        else:
            c.setFont("DejaVu-Bold", 14)
            c.setFillColor(BLUE)
            c.drawString(MARGIN, top - 9 * mm, "ViKO Consulting Engineers")
        c.setFillColor(BLUE)
        c.setFont("DejaVu-Bold", 11)
        c.drawRightString(PAGE_W - MARGIN, top - 4.5 * mm, "DCP TEST – BEARING PRESSURE REPORT")
        c.setFillColor(INK)
        c.setFont("DejaVu", 8)
        line2 = project.get("project") or ""
        if project.get("job_no"):
            line2 = f"{line2}  |  Job {project['job_no']}" if line2 else f"Job {project['job_no']}"
        c.drawRightString(PAGE_W - MARGIN, top - 9.5 * mm, line2[:110])
        c.setFillColor(INK2)
        c.drawRightString(PAGE_W - MARGIN, top - 13.5 * mm, f"Test date: {project.get('test_date', '')}")
        c.setStrokeColor(BLUE)
        c.setLineWidth(1.2)
        c.line(MARGIN, top - logo_h - 2.5 * mm, PAGE_W - MARGIN, top - logo_h - 2.5 * mm)
        # footer
        c.setStrokeColor(RULE)
        c.setLineWidth(0.5)
        c.line(MARGIN, 13 * mm, PAGE_W - MARGIN, 13 * mm)
        c.setFont("DejaVu", 7)
        c.setFillColor(INK2)
        c.drawString(MARGIN, 9 * mm, f"ViKO Consulting Engineers  •  Generated {datetime.now():%Y-%m-%d %H:%M}")
        c.restoreState()
    return on_page


# ------------------------------------------------------------------ content
def _summary_table(results: list[TestResult], q_req: Optional[float]):
    head = ["Test", "Test level", "Found.\n(mm)", "B\n(mm)", "Depth\nreached\n(mm)",
            "Weakest\nlayer (mm)", "DN\n(mm/\nblow)", "CBR\n(%)", "ViKO\n(kPa)", "Paige-\nGreen\n(kPa)"]
    if q_req:
        head.append("Meets\nreq.")
    data = [[_p(f"<b>{h}</b>".replace("\n", "<br/>"), "cell") for h in head]]
    extra = []
    for r in results:
        g = r.governing
        row = [
            _p(f"<b>{r.test.name}</b>", "cell"), _p(r.test.test_level, "cell"),
            _fmt(r.zone_top_mm), _fmt(r.test.footing_width_mm),
            _fmt(r.depth_reached_mm) + (" R" if r.test.refusal else "") + (" *" if r.depth_ok is False else ""),
            f"{g.top_mm:.0f}–{g.bottom_mm:.0f}" if g else "–",
            _fmt(g.dn, 1) if g else "–",
            ("≥110" if g.dn < DN_MIN else _fmt(g.cbr, 1)) if g else "–",
            _fmt(r.q_viko), _fmt(r.q_pg),
        ]
        if q_req:
            if g:
                ok_v, ok_p = r.q_viko >= q_req, r.q_pg >= q_req
                txt = "Both" if ok_v and ok_p else ("PG only" if ok_p else ("ViKO only" if ok_v else "No"))
                row.append(txt)
                col = GOOD if ok_v and ok_p else BAD
                extra.append(("TEXTCOLOR", (len(row) - 1, len(data)), (len(row) - 1, len(data)), col))
                extra.append(("FONT", (len(row) - 1, len(data)), (len(row) - 1, len(data)), "DejaVu-Bold", 7.3))
            else:
                row.append("–")
        data.append(row)
    ws = [20, 22, 15, 13, 18, 20, 15, 12, 14, 17]
    if q_req:
        ws.append(14)
    scale = (CONTENT_W / mm) / sum(ws)
    t = _grid_table(data, [w * scale * mm for w in ws],
                    extra=extra + [("ALIGN", (2, 1), (-1, -1), "RIGHT")])
    return t


def _readings_table(r: TestResult):
    head = ["No", "Blows", "Reading\n(mm)", "Pen.\n(mm)", "Depth\n(mm)", "DN\n(mm/\nblow)", "CBR\n(%)",
            "ViKO\n(kPa)", "P-G\n(kPa)", "Status / note"]
    data = [[_p(f"<b>{h}</b>".replace("\n", "<br/>"), "cell") for h in head]]
    data.append(["0", "–", _fmt(r.test.zero_reading_mm), "–", "0", "–", "–", "–", "–",
                 _p("Zero reading", "cell")])
    extra = []
    for inc in r.increments:
        status = inc.status + (f": {inc.note}" if inc.note else "")
        row = [str(inc.no), str(inc.blows), _fmt(inc.reading_mm), _fmt(inc.pen_mm),
               f"{inc.top_mm:.0f}–{inc.bottom_mm:.0f}",
               _fmt(inc.dn, 1), ("≥110" if inc.dn is not None and inc.dn < DN_MIN else _fmt(inc.cbr, 1)),
               _fmt(inc.q_viko), _fmt(inc.q_pg), _p(status, "cell")]
        data.append(row)
        ri = len(data) - 1
        if not inc.used:
            extra.append(("TEXTCOLOR", (0, ri), (-2, ri), INK2))
        if r.governing and inc.no == r.governing.no:
            extra.append(("FONT", (0, ri), (-2, ri), "DejaVu-Bold", 7.3))
            extra.append(("BACKGROUND", (0, ri), (-1, ri), colors.HexColor("#fde9df")))
    ws = [7, 11, 14, 12, 18, 12, 11, 12, 12, 61]
    scale = (CONTENT_W / mm) / sum(ws)
    return _grid_table(data, [w * scale * mm for w in ws],
                       extra=extra + [("ALIGN", (0, 1), (-2, -1), "RIGHT")])


def _overall_findings(results: list[TestResult], q_req: Optional[float]) -> list[str]:
    rs = [r for r in results if r.governing]
    out = []
    if not rs:
        return ["No test produced a valid reading within its assessment zone."]
    gv = min(rs, key=lambda r: r.q_viko)
    gp = min(rs, key=lambda r: r.q_pg)
    out.append(f"{len(results)} test position(s) recorded; {len(rs)} with valid readings in the assessment zone.")
    out.append(f"Lowest bearing pressure – ViKO method: <b>{gv.q_viko:.0f} kPa</b> at {gv.test.name} "
               f"(CBR {gv.cbr:.1f} %, DN {gv.governing.dn:.1f} mm/blow).")
    out.append(f"Lowest bearing pressure – Paige-Green: <b>{gp.q_pg:.0f} kPa</b> at {gp.test.name} "
               f"(DN {gp.governing.dn:.1f} mm/blow).")
    if q_req:
        fails = [r.test.name for r in rs if min(r.q_viko, r.q_pg) < q_req]
        if fails:
            out.append(f"Required bearing pressure {q_req:.0f} kPa is <b>not met</b> by both methods at: "
                       f"{', '.join(fails)}.")
        else:
            out.append(f"Required bearing pressure {q_req:.0f} kPa is met by both methods at all test positions.")
    short = [r.test.name for r in results if r.depth_ok is False]
    if short:
        out.append(f"Test depth did not reach founding + 2B at: {', '.join(short)} – ground below is not assessed.")
    none = [r.test.name for r in results if not r.governing]
    if none:
        out.append(f"No valid readings in the assessment zone at: {', '.join(none)}.")
    return out


METHOD_TEXT = [
    "<b>Test.</b> Dynamic Cone Penetrometer (standard 8 kg hammer, 575 mm drop, 60° cone). The rule reading "
    "is recorded after a known number of blows. Penetration rate DN = penetration ÷ blows (mm/blow).",
    "<b>CBR.</b> In-situ CBR from DN using ViKO Table 1 (DCP number vs in-situ CBR), interpolated linearly "
    "between table points and limited to the table range (DN 3–80 mm/blow; CBR 110–1 %). The table agrees "
    "with the Transvaal Roads Department correlation CBR = 410·DN<super>−1.27</super> within about 5 % "
    "for DN 3–60.",
    f"<b>Bearing pressure – ViKO method.</b> q = {VIKO_A}·CBR<super>{VIKO_B}</super> kPa. ViKO in-house "
    "correlation; its published source is not known.",
    f"<b>Bearing pressure – Paige-Green (2009).</b> q = {PG_A}·DN<super>{PG_B}</super> kPa, as quoted in "
    "South African DCP guidance as a general indication of bearing capacity.",
    "<b>Assessment zone.</b> Readings from founding level down to founding level + 2B (footing width) are "
    "assessed; where B is not given, all readings below founding level are assessed. Increments that overlap "
    "the zone are included. The governing value is the weakest increment (largest DN) in the zone. "
    "Readings excluded by the engineer are listed with the reason given.",
    "<b>Limitations.</b> Both bearing correlations are empirical indicators for shallow foundations and do "
    "not account for footing size and embedment, settlement, groundwater, or soil type. DCP results reflect "
    "the in-situ moisture condition at the time of testing; saturated, collapsible or expansive soils may "
    "behave very differently. Results must be read with the engineer's judgement of the exposed ground and, "
    "where warranted, confirmed by a geotechnical investigation.",
]


def build_pdf(project: dict, results: list[TestResult], q_required: Optional[float] = None,
              logo_path: Optional[str] = None) -> bytes:
    buf = io.BytesIO()
    doc = SimpleDocTemplate(buf, pagesize=A4, leftMargin=MARGIN, rightMargin=MARGIN,
                            topMargin=34 * mm, bottomMargin=18 * mm,
                            title=f"DCP report – {project.get('project', '')}", author="ViKO Consulting Engineers")
    story = []

    # --- page 1: project + summary
    story.append(_p("Project information", "h2"))
    pairs = [
        ("Project", project.get("project")), ("Job no.", project.get("job_no")),
        ("Client", project.get("client")), ("Site / location", project.get("site")),
        ("Tested by", project.get("tested_by")), ("Test date", project.get("test_date")),
        ("Report by", project.get("report_by")), ("Report date", project.get("report_date") or date.today().isoformat()),
        ("Required bearing", f"{q_required:.0f} kPa" if q_required else "Not specified"),
        ("Weather / conditions", project.get("conditions")),
    ]
    story.append(_kv_table(pairs))
    story.append(_p("Summary of results", "h2"))
    story.append(_summary_table(results, q_required))
    story.append(Spacer(1, 2))
    story.append(_p("R = DCP refusal.  * = test did not reach founding + 2B.  Weakest layer depths are below the "
                    "test start level. Values are at the weakest increment inside each assessment zone.", "small"))
    if any(r.governing for r in results):
        story.append(Spacer(1, 6))
        story.append(_fig_image(summary_figure(results, q_required), CONTENT_W / mm))
    story.append(_p("Key findings", "h2"))
    for f in _overall_findings(results, q_required):
        story.append(Paragraph(f, S["bullet"], bulletText="•"))
    if project.get("general_remarks"):
        story.append(_p("Engineer's remarks", "h2"))
        story.append(_p(project["general_remarks"].replace("\n", "<br/>")))

    # --- one page per test
    for r in results:
        story.append(PageBreak())
        t = r.test
        story.append(_p(f"Test position: {t.name}", "h1"))
        pairs = [
            ("Description", t.description), ("Test start level", t.test_level),
            ("Zero reading", f"{t.zero_reading_mm:.0f} mm"),
            ("Founding depth", f"{r.zone_top_mm:.0f} mm below test start"),
            ("Footing width B", f"{t.footing_width_mm:.0f} mm" if t.footing_width_mm else "Not given"),
            ("Assessment zone", f"{r.zone_top_mm:.0f}–{r.zone_bottom_mm:.0f} mm" if r.zone_bottom_mm is not None
             else f"Below {r.zone_top_mm:.0f} mm"),
            ("Depth reached", f"{r.depth_reached_mm:.0f} mm" + (" (refusal)" if t.refusal else "")),
            ("Readings", f"{len(r.increments)}"),
        ]
        story.append(_kv_table(pairs))
        story.append(_p("Findings", "h2"))
        for f in findings_text(r, q_required):
            story.append(Paragraph(f, S["bullet"], bulletText="•"))
        story.append(Spacer(1, 4))
        story.append(KeepTogether([_fig_image(profile_figure(r, q_required), CONTENT_W / mm * 0.85)]))
        story.append(_p("Readings", "h2"))
        story.append(_p("Highlighted row: governing (weakest) increment. Grey text: increment not used. "
                        "Depths are below the test start level.", "small"))
        story.append(Spacer(1, 2))
        story.append(_readings_table(r))

    # --- method page
    story.append(PageBreak())
    story.append(_p("Method and limitations", "h1"))
    for m in METHOD_TEXT:
        story.append(_p(m))
        story.append(Spacer(1, 5))

    deco = _decorate(project, logo_path)
    doc.build(story, onFirstPage=deco, onLaterPages=deco, canvasmaker=_NumberedCanvas)
    return buf.getvalue()
