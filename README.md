# ViKO DCP Test – Bearing Pressure App

Streamlit app for capturing Dynamic Cone Penetrometer (DCP) readings on site and printing a
ViKO-branded PDF report. Replaces the in-house Excel sheet.

## Files
| File | Purpose |
|---|---|
| `app.py` | Streamlit interface (site entry, summary, PDF download, JSON backup/restore) |
| `dcp_core.py` | Calculations – DN, CBR (ViKO Table 1), bearing pressure (ViKO method & Paige-Green), assessment zone |
| `dcp_charts.py` | Depth profile and summary charts (matplotlib) |
| `dcp_report.py` | PDF report (ReportLab) |
| `viko_logo.png` | Logo for the app sidebar and report header |
| `.streamlit/config.toml` | ViKO blue theme |
| `tests/test_core.py` | Checks against the old Excel sheet (Bases A2, A3, A4a, A4b) |

## Deploy (Streamlit Community Cloud)
1. Create a new GitHub repo and push all files (keep `.streamlit/` in the repo).
2. share.streamlit.io → **New app** → pick the repo → main file `app.py` → Deploy.

Run locally: `pip install -r requirements.txt` then `streamlit run app.py`.
Tests: `pip install pytest` then `pytest tests`.

## Using it on site
1. Sidebar: project details (and required bearing pressure if you want a pass/fail).
2. **Test setup**: name, zero reading, *founding depth below test start* (0 if testing at founding level)
   and footing width B (optional). The assessment zone is founding depth → founding + 2B.
3. **Add reading**: blows + rule reading → *Add*. Blows default to the last value used.
4. Correct anything in the Readings table; tick **Exclude** and give a reason to drop a reading.
5. **Download backup (.json)** regularly – a page reload on a phone loses unsaved data.
   *Load file* restores it.
6. **Summary & report** → *Generate PDF report* → *Download PDF*.

## Method
- DN = penetration ÷ blows (mm/blow)
- CBR from ViKO Table 1, linear interpolation, clipped to DN 3–80 (≈ CBR = 410·DN^-1.27, Transvaal Roads Dept)
- ViKO method: q = 26.16·CBR^0.664 kPa (in-house; source unknown)
- Paige-Green (2009): q = 3426.8·DN^-1.0101 kPa
- Governing value = weakest increment (largest DN) inside the assessment zone.
