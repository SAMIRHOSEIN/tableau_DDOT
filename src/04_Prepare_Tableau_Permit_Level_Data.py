#%%
# PURPOSE:
# Transform the downloaded permit records into a validated dataset
# containing one observation per new, non-renewal construction permit.
# Verify permit-level consistency, resolve repeated location records,
# and calculate approval durations in business days, excluding weekends
# and official DC holidays. Classify permits by work category and ward,
# evaluate selected assumptions, and document the preparation process.
# Generate the final dataset used to develop the Tableau dashboard.
#
# OUTPUT: Saves the Tableau-ready CSV, holiday records, multi-location
# permit summaries, data-quality results, and methodology documentation.

from pathlib import Path
import numpy as np
import pandas as pd

PROJECT_ROOT = Path(__file__).resolve().parent.parent  # Script is in src/
RAW_FILE = PROJECT_ROOT / "data" / "raw" / "fy2026_new_permits_all_api_records.csv"
OUT_DIR = PROJECT_ROOT / "data" / "processed"
AUDIT_DIR = PROJECT_ROOT / "data" / "audit"
DOCS_DIR = PROJECT_ROOT / "docs"
OUT_DIR.mkdir(parents=True, exist_ok=True)
AUDIT_DIR.mkdir(parents=True, exist_ok=True)
DOCS_DIR.mkdir(parents=True, exist_ok=True)

# The official legal holidays within FY2026, for an ordinary Monday-Friday schedule.
# 2025: https://edpm.dc.gov/issuances/legal-public-holidays-2025/
# 2026: https://edpm.dc.gov/issuances/legal-public-holidays/
LEGAL_DC_HOLIDAYS = {
    "2025-10-13": "Indigenous Peoples' Day",
    "2025-11-11": "Veterans Day",
    "2025-11-27": "Thanksgiving Day",
    "2025-12-25": "Christmas Day",
    "2026-01-01": "New Year's Day",
    "2026-01-19": "Martin Luther King Jr. Day",
    "2026-02-16": "Washington's Birthday",
    "2026-04-16": "DC Emancipation Day",
    "2026-05-25": "Memorial Day",
    "2026-06-19": "Juneteenth",
    "2026-07-03": "Independence Day (observed)",
    "2026-09-07": "Labor Day",
}
# DC government offices also closed for this one additional *administrative*
# day, which is not listed as a legal public holiday; show it separately.
# https://edpm.dc.gov/issuances/district-government-closure-friday-november-28-2025/
SPECIAL_OFFICE_CLOSURES = {"2025-11-28": "District administrative closing"}

CATEGORIES = {
    "IsExcavation": "Excavation",
    "IsFixture": "Fixture",
    "IsPaving": "Paving",
    "IsOccupancy": "Occupancy",
    "IsLandscaping": "Landscaping",
    "IsProjections": "Projections",
    "IsPSRental": "Public Space Rental",
    "IsOverHeadWork": "Overhead Work",
    "IsAnnualPermit": "Annual Permit",
}


def dc_date(series):
    """ArcGIS millisecond epoch -> DC local date, ignoring clock time."""
    return pd.to_datetime(series, unit="ms", utc=True, errors="coerce").dt.tz_convert(
        "America/New_York"
    ).dt.tz_localize(None).dt.normalize()


def busdays_exclude_application_include_approval(start, end, holiday_dates):
    """Count Mon-Fri (not on specified holidays) in (start, end]."""
    s = (start.values.astype("datetime64[D]") + np.timedelta64(1, "D"))
    e = (end.values.astype("datetime64[D]") + np.timedelta64(1, "D"))
    hols = np.asarray(sorted(holiday_dates), dtype="datetime64[D]")
    return np.busday_count(s, e, holidays=hols)


def main():
    if not RAW_FILE.exists():
        raise FileNotFoundError(f"Cannot find the Step 3 raw CSV: {RAW_FILE}")
    raw = pd.read_csv(RAW_FILE, low_memory=False, dtype={"PermitNumber": "string"})
    needed = [
        "OBJECTID", "TrackingNumber", "PermitNumber", "ApplicationDate",
        "LastApprovalDate", "IssueDate", "StatusDescription",
        "PermitTypeDescription", "RenewalDescription", "Renewal",
        "SourcePermit", "TypeDetailNames", "WorkLocationWard", "DaysToApprove",
        *CATEGORIES.keys(),
    ]
    missing = [c for c in needed if c not in raw.columns]
    if missing:
        raise ValueError(f"Expected column(s) missing in raw CSV: {missing}")
    if raw.OBJECTID.duplicated().any() or raw.TrackingNumber.isna().any():
        raise ValueError("Missing TrackingNumber or repeated OBJECTID: inspect raw file first")
    if (raw.PermitTypeDescription != "New").any():
        raise ValueError("Raw dataset contains non-'New' PermitTypeDescription; stop")

    # For permit-level analysis, dates and permit metadata must be identical
    # across all location records for the same TrackingNumber.
    invariant_cols = [
        "PermitNumber", "ApplicationDate", "LastApprovalDate", "IssueDate",
        "StatusDescription", "PermitTypeDescription", "RenewalDescription",
        "Renewal", "SourcePermit", "TypeDetailNames", "DaysToApprove",
        *CATEGORIES.keys(),
    ]
    distinct_per_key = raw.groupby("TrackingNumber")[invariant_cols].nunique(dropna=False)
    conflict = distinct_per_key.gt(1)
    if conflict.to_numpy().any():
        bad = conflict.any(axis=1)
        raise ValueError(
            f"Found {bad.sum()} TrackingNumbers with conflicting permit-level "
            f"attributes. Inspect before deduplicating: {bad[bad].index[:10].tolist()}"
        )
    if (raw.groupby("PermitNumber")["TrackingNumber"].nunique(dropna=False) > 1).any():
        raise ValueError("One PermitNumber maps to multiple TrackingNumbers: stop")

    # Keep original raw CSV untouched; one representative record per permit.
    unique = raw.sort_values("OBJECTID").drop_duplicates("TrackingNumber").copy()
    renewal_pairs = unique.groupby(["RenewalDescription", "Renewal"], dropna=False).size()
    print("RenewalDescription / Renewal-code distribution (PERMIT level):")
    print(renewal_pairs.to_string())
    # The actual source uses Renewal=1 for New, 2 for Renewal. Validate this.
    correct_pair = ((unique.RenewalDescription.eq("New") & unique.Renewal.eq(1)) |
                    (unique.RenewalDescription.eq("Renewal") & unique.Renewal.eq(2)))
    if not correct_pair.all():
        raise ValueError("Unknown/mismatched renewal labels or codes; inspect before filtering")

    # Strict reading of 'Only new permits': exclude renewed permit issues.
    main = unique.loc[unique.RenewalDescription.eq("New")].copy()

    # Document multi-location permits rather than discarding evidence of their
    # spatial coverage. Full street addresses never appear in the audit exports.
    # WorkLocationAddressID and WorkLocationFullAddress describe distinct listed
    # locations, but are not independently verified field-site visits.
    location_audit = raw.groupby("TrackingNumber").agg(
        API_Location_Rows=("OBJECTID", "size"),
        Distinct_Address_IDs=("WorkLocationAddressID", "nunique"),
        Distinct_Work_Addresses=("WorkLocationFullAddress", "nunique"),
        Distinct_Wards=("WorkLocationWard", "nunique"),
    ).reset_index()
    location_audit = location_audit.merge(
        unique[["TrackingNumber", "PermitNumber", "RenewalDescription"]],
        on="TrackingNumber", how="left", validate="one_to_one"
    )
    location_audit = location_audit.sort_values(
        ["API_Location_Rows", "TrackingNumber"], ascending=[False, True]
    )
    top_all = location_audit.head(10).copy()
    top_nonrenewal = location_audit[
        location_audit.RenewalDescription.eq("New")
    ].head(10).copy()
    top_all.to_csv(
        AUDIT_DIR / "04_top_multi_location_permits_all.csv", index=False
    )
    top_nonrenewal.to_csv(
        AUDIT_DIR / "04_top_multi_location_permits_nonrenewal.csv", index=False
    )

    selected_ids = set(main.TrackingNumber)
    raw_selected = raw.loc[raw.TrackingNumber.isin(selected_ids)]

    # Count separate LOCATION RECORDS and ward coverage without letting them
    # distort averages across permit applications.
    group = raw_selected.groupby("TrackingNumber", sort=False)
    location_counts = group.size().rename("Location_Record_Count")
    ward_lists = group.WorkLocationWard.apply(
        lambda x: sorted({int(v) for v in x.dropna().unique()})
    )
    main["Location_Record_Count"] = main.TrackingNumber.map(location_counts).astype(int)
    main["Ward_Count"] = main.TrackingNumber.map(ward_lists.apply(len)).astype(int)
    def ward_label(wards):
        if len(wards) == 0:
            return "Unknown"
        if len(wards) > 1:
            return "Multiple Wards"
        return f"Ward {wards[0]}"
    main["Ward_Segment"] = main.TrackingNumber.map(ward_lists.apply(ward_label))

    # Work type segmentation. More than one positive category is NOT forced
    # into an arbitrary single category; label it as mixed/multiple.
    flags = main[list(CATEGORIES)].fillna(0).astype(int)
    main["Work_Category_Count"] = flags.eq(1).sum(axis=1)
    main["Work_Category"] = [
        "Multiple Work Categories" if s > 1 else
        "Unclassified" if s == 0 else
        CATEGORIES[next(c for c in CATEGORIES if flags.loc[idx, c] == 1)]
        for idx, s in zip(main.index, main.Work_Category_Count)
    ]

    for src, dst in [
        ("ApplicationDate", "Application_Date_DC"),
        ("LastApprovalDate", "Approval_Date_DC"),
        ("IssueDate", "Issue_Date_DC"),
    ]:
        main[dst] = dc_date(main[src])
    invalid = (
        main.Application_Date_DC.isna() | main.Approval_Date_DC.isna() |
        main.Issue_Date_DC.isna() |
        (main.Approval_Date_DC < main.Application_Date_DC) |
        (main.Approval_Date_DC > main.Issue_Date_DC) |
        (main.Issue_Date_DC < main.Application_Date_DC)
    )
    invalid = invalid | (main.Application_Date_DC < pd.Timestamp("2025-10-01"))
    invalid = invalid | (main.Issue_Date_DC < pd.Timestamp("2025-10-01"))
    invalid = invalid | (main.Issue_Date_DC >= pd.Timestamp("2026-10-01"))
    if invalid.any():
        raise ValueError(f"{invalid.sum()} permits have invalid or non-FY2026 DC-local dates")

    main["Business_Days_To_Approve"] = busdays_exclude_application_include_approval(
        main.Application_Date_DC, main.Approval_Date_DC, LEGAL_DC_HOLIDAYS
    )
    main["Business_Days_To_Approve_With_Closure"] = busdays_exclude_application_include_approval(
        main.Application_Date_DC, main.Approval_Date_DC,
        {**LEGAL_DC_HOLIDAYS, **SPECIAL_OFFICE_CLOSURES},
    )
    main["Calendar_Days_To_Approve"] = (
        main.Approval_Date_DC - main.Application_Date_DC
    ).dt.days
    main["Application_Month"] = main.Application_Date_DC.dt.strftime("%Y-%m")
    main["Issue_Month"] = main.Issue_Date_DC.dt.strftime("%Y-%m")

    # Export only useful, readily interpretable columns (no individual names,
    # contact details, or raw addresses). Calendar-day source metric retained
    # for validation; not the requested final KPI.
    exported = [
        "TrackingNumber", "PermitNumber", "Application_Date_DC",
        "Approval_Date_DC", "Issue_Date_DC", "Application_Month", "Issue_Month",
        "Business_Days_To_Approve", "Business_Days_To_Approve_With_Closure",
        "Calendar_Days_To_Approve", "DaysToApprove", "StatusDescription",
        "PermitTypeDescription", "RenewalDescription", "TypeDetailNames",
        "Work_Category", "Work_Category_Count", "Ward_Segment", "Ward_Count",
        "Location_Record_Count", *CATEGORIES.keys(),
    ]
    for datefield in ["Application_Date_DC", "Approval_Date_DC", "Issue_Date_DC"]:
        main[datefield] = main[datefield].dt.strftime("%Y-%m-%d")
    output = main[exported].sort_values(["Application_Date_DC", "TrackingNumber"])
    csv_path = OUT_DIR / "fy2026_new_nonrenewal_permits_tableau.csv"
    output.to_csv(csv_path, index=False, encoding="utf-8-sig")

    hol_csv = AUDIT_DIR / "04_dc_holidays_used.csv"
    pd.DataFrame(
        [{"Date": date, "Holiday_or_Closure": label, "Treatment": "legal public holiday"}
         for date, label in LEGAL_DC_HOLIDAYS.items()] +
        [{"Date": date, "Holiday_or_Closure": label,
          "Treatment": "optional administrative closing; excluded only in sensitivity metric"}
         for date, label in SPECIAL_OFFICE_CLOSURES.items()]
    ).to_csv(hol_csv, index=False, encoding="utf-8-sig")

    avg_business = output.Business_Days_To_Approve.mean()
    avg_rawweighted = main["Business_Days_To_Approve"].repeat(main.Location_Record_Count).mean()
    avg_withclosure = output.Business_Days_To_Approve_With_Closure.mean()
    lines = [
        "DDOT Tableau Assessment | Step 4: FY2026 permit-level analysis preparation",
        "RAW QUERY (Step 3): ApplicationDate >= 2025-10-01; 2025-10-01 <= IssueDate < 2026-10-01; PermitTypeDescription = 'New'; no current-status filter.",
        "INTERPRETATION: Also require RenewalDescription='New' (Renewal=1) to exclude renewed permits; this is an explicit assumption that may merit a sensitivity comparison.",
        "UNIT: one TrackingNumber (= one distinct PermitNumber here), not one API location record.",
        "DATE SEMANTICS: local calendar dates in America/New_York.",
        "BUSINESS DAYS CALCULATION METHOD:",
        "  - Application date is EXCLUDED from the calculation.",
        "  - Approval date is INCLUDED if it is a business day.",
        "  - Saturdays, Sundays, and official DC holidays are EXCLUDED.",
        "  - Same-day approval = 0 business days.",
        "SPECIAL CLOSURE: Nov 28, 2025 was a DC government administrative closure (not a legal holiday); separate alternative metric excludes it.",
        "CURRENT STATUS: retained regardless of later expiration/suspension/revocation, as long as IssueDate is in FY2026.",
        "SEGMENTATION: Work_Category='Multiple Work Categories' if flags overlap; Ward_Segment='Multiple Wards' for permit touching >1 ward.",
        "OFFICIAL HOLIDAYS: https://edpm.dc.gov/issuances/legal-public-holidays-2025/ ; https://edpm.dc.gov/issuances/legal-public-holidays/",
        "OFFICIAL CLOSURE: https://edpm.dc.gov/issuances/district-government-closure-friday-november-28-2025/",
        "",
        f"Raw location-level API records: {len(raw):,}",
        f"Unique permits with PermitTypeDescription='New' (includes renewals): {len(unique):,}",
        f"Of those, RenewalDescription='Renewal' (excluded from main): {len(unique) - len(main):,}",
        f"Non-renewal permits included in main dataset: {len(main):,}",
        f"Original location records corresponding to those permits: {len(raw_selected):,}",
        f"Invalid included permit dates: {int(invalid.sum()):,}",
        f"Multi-ward permits: {(main.Ward_Count > 1).sum():,}",
        f"Unknown-ward permits: {(main.Ward_Count == 0).sum():,}",
        f"Permits involving multiple work categories: {(main.Work_Category_Count > 1).sum():,}",
        f"Mean legal-holiday-only BUSINESS DAYS (unweighted permits): {avg_business:.3f}",
        f"Mean business days if erroneously weighted by location-record count: {avg_rawweighted:.3f}",
        f"Mean business days INCLUDING Nov 28 administrative closure as a non-business day: {avg_withclosure:.3f}",
        "",
        "Current status counts (PERMITS, not API records):",
        *[f"  {k}: {v:,}" for k, v in output.StatusDescription.value_counts().items()],
        "Work category counts (PERMITS):",
        *[f"  {k}: {v:,}" for k, v in output.Work_Category.value_counts().items()],
        "",
        "TOP 10 MULTI-LOCATION PERMITS (ALL TYPES, INCLUDING RENEWALS):",
        *[f"  TrackingNumber {int(r.TrackingNumber)}: "
          f"{int(r.API_Location_Rows)} API rows; "
          f"{int(r.Distinct_Work_Addresses)} distinct listed addresses; "
          f"{int(r.Distinct_Wards)} wards; "
          f"{r.RenewalDescription}"
          for r in top_all.itertuples()],
        "",
        "TOP 10 MULTI-LOCATION NON-RENEWAL PERMITS (MAIN ANALYSIS):",
        *[f"  TrackingNumber {int(r.TrackingNumber)}: "
          f"{int(r.API_Location_Rows)} API rows; "
          f"{int(r.Distinct_Work_Addresses)} distinct listed addresses; "
          f"{int(r.Distinct_Wards)} wards"
          for r in top_nonrenewal.itertuples()],
        "NOTE: Listed addresses are distinct in the source. They do not necessarily"
        " indicate an equal number of physically independent construction projects.",
        "",
        # f"Tableau-ready CSV: {csv_path}",
        f"Tableau-ready CSV: data/processed/{csv_path.name}",
    ]
    report_path = AUDIT_DIR / "04_permit_level_preparation_summary.txt"
    report_path.write_text("\n".join(lines) + "\n", encoding="utf-8")

    # Plain-language, reusable documentation for the Tableau deliverable.
    def markdown_top(df):
        return "\n".join(
            f"| {int(r.TrackingNumber)} | {int(r.API_Location_Rows)} | "
            f"{int(r.Distinct_Work_Addresses)} | {int(r.Distinct_Wards)} | "
            f"{r.RenewalDescription} |" for r in df.itertuples()
        )
    md = f"""# DDOT FY2026 Tableau assessment: methodology and data quality

## Study population

The source query filters applications dated on or after 2025-10-01,
issues dated 2025-10-01 through 2026-09-30 (local DC calendar dates), and
`PermitTypeDescription = New`. Current permit status is not filtered, so
previously issued permits subsequently marked Expired, Suspended, or Revoked
remain included. The query returned **{len(raw):,} location-level API rows**
representing **{len(unique):,} unique permits**. The main assessment dataset
additionally restricts `RenewalDescription = New` rather than Renewal, leaving
**{len(main):,} non-renewal permits**. This is an explicitly documented
interpretation of 'new permits' and should be confirmed against the assignment.

## Why duplicate IDs matter

The API's unit of record may be a permit-location combination. A permit with
multiple recorded addresses appears on multiple API rows, but should contribute
only one observation to a permit-level approval-time mean. All permit-level
attributes were tested for consistency within each `TrackingNumber` before
collapsing to one row per permit; no contradictory values were found.
The raw download remains unchanged. The distinct locations have not been
asserted to represent physically separate construction projects.

### Examples: most repeated permits across the full source query

| TrackingNumber | API rows | Distinct listed addresses | Distinct wards | Renewal type |
|---|---:|---:|---:|---|
{markdown_top(top_all)}

For example, `502829` has 176 location-level records with 176 distinct listed
addresses and is a **Renewal**; it is therefore not in the main non-renewal
dashboard population. An example from the main population is
`{int(top_nonrenewal.iloc[0].TrackingNumber)}` with
{int(top_nonrenewal.iloc[0].API_Location_Rows)} rows and
{int(top_nonrenewal.iloc[0].Distinct_Work_Addresses)} listed addresses.

## Outcome metric

The outcome is *business days to approve*, from the DC-local application date
to the DC-local last-approval date, excluding the application date and including
the approval date when it is a business day. Saturday, Sunday, and legal District
public holidays are excluded using NumPy's `busday_count` and the dated
`LEGAL_DC_HOLIDAYS` lookup in the Python script. A same-day approval has value 0.

The legal-holiday-only average for the main population is **{avg_business:.2f}
business days** (median **{output.Business_Days_To_Approve.median():.0f}**),
versus **{avg_rawweighted:.2f}** if each location row were incorrectly given
an equal weight. An alternative metric also excludes the District's administrative
closing on November 28, 2025, and produces **{avg_withclosure:.2f}** business days.
That extra closing day is *not* part of the main metric.

## Geography and work type

To avoid arbitrary assignment, permits appearing in multiple wards are labeled
`Multiple Wards` (**{int((main.Ward_Count > 1).sum())} permits**); missing ward
coverage is `Unknown` (**{int((main.Ward_Count == 0).sum())} permits**). Permits
flagged for multiple work categories are classified `Multiple Work Categories`
(**{int((main.Work_Category_Count > 1).sum())} permits**) rather than assigned
arbitrarily to only one activity.

## Source traceability and files

- Original query output: `data/raw/fy2026_new_permits_all_api_records.csv`
- Final Tableau input: `data/processed/fy2026_new_nonrenewal_permits_tableau.csv`
- Holiday listing: `data/audit/04_dc_holidays_used.csv`
- Machine-readable multi-location examples: `data/audit/04_top_multi_location_permits_all.csv`
  and `data/audit/04_top_multi_location_permits_nonrenewal.csv`
- Full computational audit: `data/audit/04_permit_level_preparation_summary.txt`
- Official DC holiday references:
  https://edpm.dc.gov/issuances/legal-public-holidays-2025/
  and https://edpm.dc.gov/issuances/legal-public-holidays/

**Limitations:** `LastApprovalDate` is interpreted as the approval event and
`RenewalDescription = New` as non-renewal; document these choices in the Tableau
submission. Current permit status describes status when fetched, not necessarily
status when the permit was first issued. FY2026 is the issue-date cohort, not a
cohort of all applications resolved in FY2026.
"""
    docs_path = DOCS_DIR / "04_Methodology_and_Data_Quality.md"
    docs_path.write_text(md, encoding="utf-8")
    print("\n".join(lines))
    print("\nDocumentation saved:", docs_path)
    print("\nHoliday list saved:", hol_csv)
    print("\nDONE: Review the printed assumptions before importing this CSV into Tableau.")

if __name__ == "__main__":
    main()
