# DDOT FY2026 Tableau assessment: methodology and data quality

## Study population

The source query filters applications dated on or after 2025-10-01,
issues dated 2025-10-01 through 2026-09-30 (local DC calendar dates), and
`PermitTypeDescription = New`. Current permit status is not filtered, so
previously issued permits subsequently marked Expired, Suspended, or Revoked
remain included. The query returned **28,277 location-level API rows**
representing **5,378 unique permits**. The main assessment dataset
additionally restricts `RenewalDescription = New` rather than Renewal, leaving
**2,025 non-renewal permits**. This is an explicitly documented
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
| 498676 | 176 | 176 | 1 | Renewal |
| 502829 | 176 | 176 | 1 | Renewal |
| 500255 | 90 | 90 | 1 | Renewal |
| 500365 | 85 | 85 | 1 | Renewal |
| 500941 | 85 | 85 | 1 | Renewal |
| 500963 | 83 | 83 | 1 | Renewal |
| 497055 | 75 | 75 | 1 | New |
| 498867 | 68 | 68 | 1 | Renewal |
| 500713 | 68 | 68 | 1 | Renewal |
| 498536 | 67 | 67 | 1 | Renewal |

For example, `502829` has 176 location-level records with 176 distinct listed
addresses and is a **Renewal**; it is therefore not in the main non-renewal
dashboard population. An example from the main population is
`497055` with
75 rows and
75 listed addresses.

## Outcome metric

The outcome is *business days to approve*, from the DC-local application date
to the DC-local last-approval date, excluding the application date and including
the approval date when it is a business day. Saturday, Sunday, and legal District
public holidays are excluded using NumPy's `busday_count` and the dated
`LEGAL_DC_HOLIDAYS` lookup in the Python script. A same-day approval has value 0.

The legal-holiday-only average for the main population is **29.33
business days** (median **21**),
versus **44.69** if each location row were incorrectly given
an equal weight. An alternative metric also excludes the District's administrative
closing on November 28, 2025, and produces **29.31** business days.
That extra closing day is *not* part of the main metric.

## Geography and work type

To avoid arbitrary assignment, permits appearing in multiple wards are labeled
`Multiple Wards` (**14 permits**); missing ward
coverage is `Unknown` (**137 permits**). Permits
flagged for multiple work categories are classified `Multiple Work Categories`
(**76 permits**) rather than assigned
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
