#%%
"""DDOT CS-12 Tableau assessment: inspect FY2026 new permits.

This script queries a public ArcGIS REST service and prints the exact
selection rules, matching *record* count, current-status distribution,
and a 15-record sample. It deliberately does NOT restrict current status
to 'Issued', because issued permits may subsequently expire or change
status. No records are deduplicated or exported at this stage.

Dependencies: requests, pandas
Run: python 02_Explore_FY2026_Permits.py
"""

import json

import pandas as pd
import requests

API_URL = (
    "https://maps2.dcgis.dc.gov/dcgis/rest/services/"
    "DCGIS_APPS/DDOT_TOPS/MapServer/23/query"
)

# Fiscal year 2026: October 1, 2025 - September 30, 2026 (DC local dates)
APPLICATION_START = "2025-10-01"
ISSUE_START = "2025-10-01"
ISSUE_END_EXCLUSIVE = "2026-10-01"
PERMIT_TYPE = "New"

# This SQL is the only selection filter used for all queries below.
WHERE = (
    f"ApplicationDate >= TIMESTAMP '{APPLICATION_START} 00:00:00' "
    f"AND IssueDate >= TIMESTAMP '{ISSUE_START} 00:00:00' "
    f"AND IssueDate < TIMESTAMP '{ISSUE_END_EXCLUSIVE} 00:00:00' "
    f"AND PermitTypeDescription = '{PERMIT_TYPE}'"
)


def query_ddot(extra_params: dict) -> dict:
    """Query ArcGIS and raise an informative error if the query fails."""
    params = {"where": WHERE, "f": "json", **extra_params}
    response = requests.get(API_URL, params=params, timeout=90)
    response.raise_for_status()
    result = response.json()
    if "error" in result:
        raise RuntimeError(f"DDOT ArcGIS API error: {result['error']}")
    return result


def print_scope() -> None:
    print("=" * 78)
    print("DDOT TABLEAU ASSESSMENT | FY2026 NEW CONSTRUCTION PERMITS")
    print("=" * 78)
    print("EXACT FILTERS APPLIED TO EVERY QUERY:")
    print(f"  1. ApplicationDate >= {APPLICATION_START} (DC local calendar date)")
    print(f"  2. IssueDate >= {ISSUE_START} (FY2026 begins)")
    print(f"  3. IssueDate <  {ISSUE_END_EXCLUSIVE} (FY2026 ends Sep 30, 2026)")
    print(f"  4. PermitTypeDescription = '{PERMIT_TYPE}'")
    print("  5. Current StatusDescription: NOT filtered")
    print("     (Previously issued permits may now be expired/suspended/revoked.)")
    print("\nNOTE: These are matching API RECORDS, not distinct permits.")
    print("      Duplicate tracking numbers will be investigated next.")
    print("\nSQL WHERE CLAUSE:")
    print(f"  {WHERE}")


def display_count() -> int:
    result = query_ddot({"returnCountOnly": "true"})
    count = int(result["count"])
    print("\n" + "-" * 78)
    print("A. NUMBER OF RECORDS MATCHING ALL FOUR DATE/TYPE FILTERS")
    print("   (NO CURRENT-STATUS FILTER; NOT YET DEDUPLICATED)")
    print("-" * 78)
    print(f"Matched API records: {count:,}")
    return count


def display_status_breakdown(expected_count: int) -> None:
    result = query_ddot({
        "groupByFieldsForStatistics": "StatusDescription",
        "outStatistics": json.dumps([{
            "statisticType": "count",
            "onStatisticField": "OBJECTID",
            "outStatisticFieldName": "RecordCount",
        }]),
        "returnGeometry": "false",
    })
    rows = [feature["attributes"] for feature in result.get("features", [])]
    rows.sort(key=lambda item: int(item.get("RecordCount") or 0), reverse=True)

    print("\n" + "-" * 78)
    print("B. CURRENT STATUS BREAKDOWN OF THE MATCHED FY2026 NEW-PERMIT RECORDS")
    print("   (Statuses are DESCRIPTIVE here; no status was excluded.)")
    print("-" * 78)
    print(f"{'Current status':<30}{'API records':>16}{'Share of records':>20}")
    for row in rows:
        status = row.get("StatusDescription") or "[Missing status]"
        n = int(row.get("RecordCount") or 0)
        share = (100 * n / expected_count) if expected_count else 0.0
        print(f"{status:<30}{n:>16,}{share:>19.2f}%")

    total_in_groups = sum(int(item.get("RecordCount") or 0) for item in rows)
    print("-" * 66)
    print(f"{'TOTAL ACROSS STATUS GROUPS':<30}{total_in_groups:>16,}")
    print("\nInterpretation: 'Permit Expired' can still have a FY2026 IssueDate.")
    print("This report describes status NOW, not status on the issue date.")
    if total_in_groups != expected_count:
        print("WARNING: Status group totals do not match the record count.")


def display_sample() -> None:
    result = query_ddot({
        "outFields": (
            "OBJECTID,TrackingNumber,PermitNumber,ApplicationDate,"
            "LastApprovalDate,IssueDate,StatusDescription,"
            "PermitTypeDescription,TypeDetailNames,DaysToApprove,WorkLocationWard"
        ),
        "returnGeometry": "false",
        "resultRecordCount": 15,
        "orderByFields": "OBJECTID ASC",
    })
    records = [item["attributes"] for item in result.get("features", [])]
    print("\n" + "-" * 78)
    print("C. FIRST 15 MATCHED API RECORDS (SAMPLE ONLY, NOT ALL PERMITS)")
    print("   Dates displayed in the America/New_York time zone.")
    print("-" * 78)
    if not records:
        print("No matched records returned.")
        return
    frame = pd.DataFrame(records)
    for field in ["ApplicationDate", "LastApprovalDate", "IssueDate"]:
        if field in frame:
            frame[field] = (
                pd.to_datetime(frame[field], unit="ms", utc=True, errors="coerce")
                .dt.tz_convert("America/New_York")
                .dt.date
            )
    columns = [
        "OBJECTID", "TrackingNumber", "ApplicationDate",
        "LastApprovalDate", "IssueDate", "StatusDescription", "DaysToApprove"
    ]
    print(frame[[name for name in columns if name in frame]].to_string(index=False))
    print("\nNOTE: DaysToApprove is the source field; it is NOT our final")
    print("      business-day metric. No average is calculated in this script.")


def main() -> None:
    print_scope()
    n = display_count()
    display_status_breakdown(n)
    display_sample()
    print("\nFINISHED: Data exploration only. No cleaning/deduplication applied.")


if __name__ == "__main__":
    main()
