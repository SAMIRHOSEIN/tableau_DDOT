# DDOT FY2026 Construction Permit Approval | Tableau Assessment

## Purpose and deliverable

This submission analyzes **business days from application to last recorded approval** for new, non-renewal DDOT Public Space Construction Permits issued during fiscal year 2026. It provides an overall average and comparisons by work category, ward, issue month, and approval-duration band. The analysis describes differences; it does **not** estimate causes or imply a DDOT service-level deadline.

**Start here:** Open `tableau/DDOT_tableau_test.twbx` in Tableau Desktop. The `.twbx` is the portable deliverable and must contain the underlying CSV. The source `.twb` alone is not portable; see the packaging checks below when rebuilding the deliverable. The saved Tableau input is `data/processed/fy2026_new_nonrenewal_permits_tableau.csv`. Read `docs/DDOT_FY2026_Tableau_Assessment.pdf` for the methodology, limitations, and figures; the `.docx` is an editable copy.

## Key findings in the saved assessment snapshot

- **2,025 unique permits** (one observation per TrackingNumber/PermitNumber).
- **29.33 mean business days** to last approval; median **21** days.
- **762 permits (37.6%)** took more than 30 business days. This 30-day threshold is an analytical reference, **not** an official DDOT standard.
- All findings refer to the **saved data snapshot**. Refreshing the live API can change the cohort or fields and requires rerunning verification and updating the report/workbook.

## Analysis rules and limitations

1. **Source and dates:** Construction Permit layer `https://maps2.dcgis.dc.gov/dcgis/rest/services/DCGIS_APPS/DDOT_TOPS/MapServer/23`. Include applications on or after 2025-10-01 and issue dates from 2025-10-01 through 2026-09-30. Dates are interpreted in `America/New_York` before day-based calculations.
2. **New, issued permits:** Filter `PermitTypeDescription = 'New'`, and exclude records labeled `RenewalDescription = 'Renewal'`. The additional `RenewalDescription = 'New'` criterion is an explicit interpretation of the assessment's word **new**. A permit with a FY2026 issue date remains in scope even if its *current* status later became `Permit Expired`, `Suspended`, or `Revoked`.
3. **Permit-level analysis:** Source API records describe permit locations, and many `TrackingNumber` values repeat. Only one permit-level record contributes to each overall/category/ward mean. Keep location counts and multi-ward coverage separately. Do not average all original location records as if each were an independent permit.
4. **Approval milestone:** `LastApprovalDate` is treated as the recorded approval event. This is an approximation of the complete workflow, not evidence about time spent by DDOT versus waiting for applicant action.
5. **Business-day convention:** Count Monday through Friday **after** the local application date through the local last-approval date, excluding statutory/observed DC legal holidays. Same-day approval is zero. November 28, 2025, an additional administrative office closure, is excluded only in a *separate sensitivity metric*, not the primary KPI. Dates/holidays are documented in `src/04_Prepare_Tableau_Permit_Level_Data.py` and `data/audit/04_dc_holidays_used.csv`.
6. **Segmentation:** Permit activity flags define `Work_Category`; overlapping flags are `Multiple Work Categories`. Ward is based on all recorded permit locations; multiple wards are `Multiple Wards`, and no known ward is `Unknown`. Comparisons are descriptive and unadjusted for application complexity or case mix. Small categories/monthly cohorts should be interpreted cautiously.

## Folder guide

| Path | Purpose |
|---|---|
| `tableau/DDOT_tableau_test.twbx` | **Required packaged, portable workbook** (create and test in Tableau Desktop) |
| `tableau/DDOT_tableau_test.twb` | Optional editable/unpackaged workbook source; has a local CSV connection and is **not** a substitute for `.twbx` |
| `data/processed/fy2026_new_nonrenewal_permits_tableau.csv` | Saved 2,025-row, 29-column Tableau input |
| `data/audit/` | Download checks, holiday reference, and preparation summaries |
| `docs/DDOT_FY2026_Tableau_Assessment.pdf` | Primary technical report |
| `docs/DDOT_FY2026_Tableau_Assessment.docx` | Editable version of the same report |
| `src/01_Explore_DDOT_Permits.py` | Initial API and field exploration (optional) |
| `src/02_Explore_FY2026_Permits.py` | FY2026 source-filter exploration (optional) |
| `src/03_Download_and_Audit_FY2026_New_Permits.py` | Optional full raw-data download and record-level audit; requires network |
| `src/04_Prepare_Tableau_Permit_Level_Data.py` | Transform the saved raw CSV into permit-level Tableau data; requires `data/raw/...csv` |
| `data/raw/fy2026_new_permits_all_api_records.csv` | Optional original 28,277-row source snapshot for **private ZIP only**, needed to reproduce Step 4 without downloading again |

## How to reproduce the data on Windows 11

Install **Python 3.10+** and use the following from the project root (`tableau_TODD`). In PowerShell:

```powershell
py -m venv .venv
.\.venv\Scripts\Activate.ps1
python -m pip install -r requirements.txt

# With the included raw CSV, prepare the saved Tableau input without internet:
python src/04_Prepare_Tableau_Permit_Level_Data.py

# OPTIONAL: Download a fresh version from the public DDOT ArcGIS API first:
# python src/03_Download_and_Audit_FY2026_New_Permits.py
# python src/04_Prepare_Tableau_Permit_Level_Data.py
```

All scripts use `pathlib` to resolve paths from their own locations. Step 3 writes `data/raw/fy2026_new_permits_all_api_records.csv`; Step 4 reads **that same path** and generates the processed file, audits, and `docs/04_Methodology_and_Data_Quality.md`. Steps 1 and 2 only print exploratory results. Network access to the DCGIS REST endpoint is needed for Steps 1-3; **Step 4 runs offline if the raw CSV is present**.

After rerunning Step 4, reopen Tableau and refresh the CSV connection if needed. The final report and dashboard labels refer to the documented saved snapshot, so do not regenerate the input immediately before submission without validating the results again.

## Make and test the required packaged workbook

1. Open `tableau/DDOT_tableau_test.twb` on the computer that has the project data (if prompted, reconnect it to `data/processed/fy2026_new_nonrenewal_permits_tableau.csv`).
2. In Tableau Desktop choose **File → Save As** and save a **Tableau Packaged Workbook (`.twbx`)** as `tableau/DDOT_tableau_test.twbx`. Ensure the CSV data source is included in the package.
3. Close Tableau, temporarily rename or move your local `data/processed/` directory, then open the saved `.twbx`. The five worksheets and the dashboard should display **2,025** permits and an overall mean of **29.33** business days without a missing-file prompt. Restore the processed directory afterward.
4. Test dashboard selections, clear filters, and check title and footnote text. Use the `.twbx` in the final assessment ZIP even if you also keep the `.twb` source.

## Data sharing and version control

The source is publicly available according to DDOT's assessment, and DDOT permits a supplementary GitHub link, but the **full raw CSV contains named people/organizations and precise addresses**, and the existing repository may retain raw data in **past commits**. **Do not publish the existing repository or make it public without reviewing and removing sensitive/raw files from all exposed history and checking applicable data terms.** This project's `.gitignore` excludes `data/raw/` for future Git additions; it does **not** delete material already committed.

The private assessment ZIP can retain the raw CSV to support offline reproduction. For a public portfolio repository, prefer the final processed, purpose-limited CSV, scripts, report, and workbook, after checking that the workbook package and commit history also contain no raw or unintended personal information. Keep the Git repository's `.git/` directory **out of the ZIP sent to DDOT**.

## Required submission naming

Submit a parent `FirstName_MiddleInitial_LastName_CS12_DataScientist_Tests.zip` containing separate per-test archives named `FirstName_MiddleInitial_LastName_Tableau.zip`, `FirstName_MiddleInitial_LastName_GIS.zip`, and `FirstName_MiddleInitial_LastName_Python.zip` (include only the tests you are submitting). This project folder is the *contents* of the Tableau-specific ZIP and should not include a `.git/` directory. DDOT's instructions govern final submission.
