# DDOT FY2026 Construction Permit Approval Analysis | Tableau Assessment

**Prepared by:** Amir Moayyedi  
**Assessment:** DDOT CS-12 Data Scientist — Tableau  
**Primary deliverable:** [`tableau/DDOT_tableau_test.twbx`](tableau/DDOT_tableau_test.twbx)

## 1. Project overview

This project estimates the **average number of business days from application to last recorded approval** for new, non-renewal DDOT Public Space Construction Permits issued in fiscal year (FY) 2026. The Tableau dashboard presents the overall average and descriptive comparisons by work category, ward, issue month, and approval-duration group.

The purpose is to help identify segments for follow-up investigation. The comparisons are **descriptive**, not causal, and no analytical threshold presented here should be interpreted as an official DDOT processing standard.

**To review the assessment without running Python:** Open `tableau/DDOT_tableau_test.twbx` in Tableau Desktop, then read `docs/DDOT_FY2026_Tableau_Assessment.pdf` for the methodology, findings, visualizations, and limitations. The `.twbx` contains the processed CSV data used by the workbook.

## 2. Saved-data results

| Measure | Result |
|---|---:|
| Location-level API records downloaded | 28,277 |
| Unique permits with `PermitTypeDescription = 'New'`, before excluding renewals | 5,378 |
| Unique new, non-renewal permits in the final analysis | **2,025** |
| Mean business days to last approval | **29.33** |
| Median business days to last approval | **21** |
| Permits with more than 30 business days | **762 (37.6%)** |

These figures describe the **included data snapshot**, not an automatically updating live dashboard. Re-downloading the source in the future may change the records and results.

## 3. Data source, population, and calculation

**Source:** DDOT Construction Permits, DCGIS ArcGIS REST service, layer 23:  
https://maps2.dcgis.dc.gov/dcgis/rest/services/DCGIS_APPS/DDOT_TOPS/MapServer/23

**Selection criteria:**

- Application date on or after October 1, 2025.
- Issue date between October 1, 2025, and September 30, 2026, inclusive.
- `PermitTypeDescription = 'New'`.
- Additional explicit interpretation of *new*: retain `RenewalDescription = 'New'` (the source encodes this as `Renewal = 1`) and exclude renewals. This interpretation is documented because the assessment did not supply a data dictionary.
- Do not filter by *current* status. A permit issued during FY2026 remains included even if its status subsequently changed to expired, suspended, or revoked.

**Unit of analysis:** One distinct permit (`TrackingNumber`, corresponding one-to-one with `PermitNumber` in this snapshot). The API contains multiple location records for some permits. These are checked and collapsed to one permit-level observation so multi-location permits do not receive disproportionate weight in averages. Location counts and ward coverage are retained for context.

**Business-day KPI:** `Business_Days_To_Approve` is calculated from the DC-local application date to the DC-local `LastApprovalDate`. The application date is excluded; the approval date is included when it is a business day. Saturdays, Sundays, and applicable District legal/observed holidays are excluded. A same-day approval has zero business days. November 28, 2025, a special administrative office closure, is excluded only in a **separate sensitivity metric**, not in the primary KPI.

`LastApprovalDate` is the available approval milestone. The resulting duration is not a measure of DDOT-only staff processing time; it can include other steps and waiting periods. The source's `DaysToApprove` field is retained in the processed dataset for reference, but is **not** the business-day KPI used in the dashboard.

**Segmentation:** Overlapping work-type flags are grouped as `Multiple Work Categories`; permits spanning multiple wards are labeled `Multiple Wards`; records without a known ward are labeled `Unknown`. These choices avoid assigning a multi-location or multi-category permit arbitrarily to one category.

## 4. Project files

```text
tableau_TODD/
├── README.md
├── requirements.txt
├── src/
│   ├── 01_Explore_DDOT_Permits.py
│   ├── 02_Explore_FY2026_Permits.py
│   ├── 03_Download_and_Audit_FY2026_New_Permits.py
│   └── 04_Prepare_Tableau_Permit_Level_Data.py
├── data/
│   ├── raw/
│   │   └── fy2026_new_permits_all_api_records.csv
│   ├── processed/
│   │   └── fy2026_new_nonrenewal_permits_tableau.csv
│   └── audit/
│       └── [download, duplicate-ID, holiday, and preparation checks]
├── tableau/
│   ├── DDOT_tableau_test.twbx
│   └── DDOT_tableau_test.twb
└── docs/
    ├── DDOT_FY2026_Tableau_Assessment.pdf
    └── DDOT_FY2026_Tableau_Assessment.docx
```

- **`.twbx`**: self-contained packaged Tableau workbook, with embedded processed CSV; **use this file for evaluation**.
- **`.twb`**: unpackaged Tableau source file, retained for editing; its local data path may not work on a different computer. It is not a substitute for `.twbx`.
- **`data/raw/`**: saved original API extraction, provided to allow offline reproduction of the processing step.
- **`data/processed/`**: final 2,025-row, 29-column Tableau input.
- **`data/audit/`**: traceability and validation results, including duplicate-identifier summaries and the DC holiday list.
- **`docs/`**: technical report as PDF and editable Word document. Script 04 also generates `docs/04_Methodology_and_Data_Quality.md` when run; this extra generated document need not be present in the submitted snapshot.

## 5. Reproduce the results (Windows 11)

**Requirements:** Python 3.10 or later and the packages listed in `requirements.txt` (`numpy`, `pandas`, `requests`). Tableau Desktop is required to open or edit the workbook and is installed separately.

Open PowerShell **in the `tableau_TODD` directory**, then run:

```powershell
py -m venv .venv
.\.venv\Scripts\python.exe -m pip install -r requirements.txt

# Re-create the Tableau input and audits from the included raw CSV (no internet required):
.\.venv\Scripts\python.exe src/04_Prepare_Tableau_Permit_Level_Data.py
```

Script 04 reads `data/raw/fy2026_new_permits_all_api_records.csv` and writes:

- `data/processed/fy2026_new_nonrenewal_permits_tableau.csv`;
- `data/audit/04_permit_level_preparation_summary.txt` and associated holiday/multi-location audit CSV files;
- `docs/04_Methodology_and_Data_Quality.md`.

With the provided raw snapshot, the expected output is **2,025 permits**, **29 columns**, and approximately **29.33 mean business days**. Script 04 performs input validation and stops if required fields or permit-level consistency checks fail.

**Optional live-source workflow** (requires access to the DCGIS API):

```powershell
.\.venv\Scripts\python.exe src/01_Explore_DDOT_Permits.py
.\.venv\Scripts\python.exe src/02_Explore_FY2026_Permits.py
.\.venv\Scripts\python.exe src/03_Download_and_Audit_FY2026_New_Permits.py
.\.venv\Scripts\python.exe src/04_Prepare_Tableau_Permit_Level_Data.py
```

Steps 01 and 02 are exploratory and print information to the terminal. Step 03 downloads matching API records to `data/raw/` and generates the initial data-quality audits. Step 04 uses those records to generate the final Tableau-ready dataset. **Step 03 overwrites the saved raw CSV with a fresh download**; if the live source has changed, results may differ from the submitted report and packaged workbook. For verification of the *submitted* findings, run **Step 04 only** using the included raw CSV.

All project file paths used by Scripts 03 and 04 are resolved relative to the script directory, rather than depending on the original author's computer or drive letter.

## 6. Tableau workbook verification

1. Open `tableau/DDOT_tableau_test.twbx` in Tableau Desktop. The packaged workbook contains **five worksheets and one dashboard**.
2. Confirm that the workbook opens without prompting for a local `H:` or `G:` drive and shows the saved analysis of **2,025 permits** with an overall average of approximately **29.33 business days**.
3. Check the work-category, ward, monthly, and duration-group views and try the dashboard's interactive filters.
4. If editing the unpackaged `.twb`, reconnect its data source to `data/processed/fy2026_new_nonrenewal_permits_tableau.csv`, then save a new **Tableau Packaged Workbook (`.twbx`)**. Reopen the `.twbx` without relying on the original CSV path before sharing it.

## 7. Interpretation and responsible sharing

These descriptive comparisons do not adjust for permit complexity, staffing, applicant responses, or other possible explanatory factors. Small categories or periods may have unstable averages. The report explains the assumptions and additional sensitivity checks.

The full raw CSV includes potentially identifying owner, applicant, permittee, and address information. Retain it in the private DDOT submission when needed for offline reproduction, but **review applicable source terms and data content before publishing the raw CSV, workbook contents, or existing Git history in a public repository**. The `.git/` directory itself is not part of the deliverable and should be excluded from the ZIP sent to DDOT.

## 8. Submission

The Tableau deliverable should be packaged as a separate ZIP according to the assessment's naming pattern:

`FirstName_MiddleInitial_LastName_Tableau.zip`

It should be placed in the overall `FirstName_MiddleInitial_LastName_CS12_DataScientist_Tests.zip` package with whichever other assessment components are being submitted. The official DDOT assessment instructions take precedence if any packaging details change.
