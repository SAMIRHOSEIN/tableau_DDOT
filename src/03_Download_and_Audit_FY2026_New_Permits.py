#%%
# PURPOSE:
# Download all construction permit records satisfying the FY2026
# selection criteria from the DDOT ArcGIS REST API using batch requests.
# Verify download completeness, examine repeated permit identifiers,
# and assess the consistency of application, approval, and issue dates.
# Preserve all source records for subsequent permit-level processing
# while documenting data-quality issues and duplicate record groups.
#
# OUTPUT: Saves the complete raw dataset, duplicate-identifier reports,
# and a data-quality audit summary.

from pathlib import Path
import time

import pandas as pd
import requests

API_URL = (
    "https://maps2.dcgis.dc.gov/dcgis/rest/services/"
    "DCGIS_APPS/DDOT_TOPS/MapServer/23/query"
)

# EXACTLY the same eligibility filter as Step 2; current status is NOT filtered.
WHERE = (
    "ApplicationDate >= TIMESTAMP '2025-10-01 00:00:00' "
    "AND IssueDate >= TIMESTAMP '2025-10-01 00:00:00' "
    "AND IssueDate < TIMESTAMP '2026-10-01 00:00:00' "
    "AND PermitTypeDescription = 'New'"
)
CHUNK_SIZE = 250  # Below the service limit; small enough for reliable retries.
MAX_ATTEMPTS = 4

SCRIPT_FOLDER = Path(__file__).resolve().parent
PROJECT_ROOT = SCRIPT_FOLDER.parent
RAW_DIR = PROJECT_ROOT / "data" / "1_raw"
AUDIT_DIR = PROJECT_ROOT / "data" / "audit"

session = requests.Session()
session.headers.update({"User-Agent": "DDOT-CS12-Tableau-Assessment/1.0"})


def api_query(params: dict) -> dict:
    """ArcGIS REST query with retry and readable error messages."""
    payload = {"f": "json", **params}
    last_error = None
    for attempt in range(1, MAX_ATTEMPTS + 1):
        try:
            # POST avoids overly long URLs when sending many OBJECTIDs.
            response = session.post(API_URL, data=payload, timeout=90)
            response.raise_for_status()
            data = response.json()
            if "error" in data:
                raise RuntimeError(f"ArcGIS error: {data['error']}")
            return data
        except (requests.RequestException, ValueError, RuntimeError) as error:
            last_error = error
            if attempt < MAX_ATTEMPTS:
                print(f"  API request failed ({error}); retry {attempt}/{MAX_ATTEMPTS - 1}", flush=True)
                time.sleep(attempt * 2)
    raise RuntimeError(f"ArcGIS API request failed after {MAX_ATTEMPTS} attempts: {last_error}")


def local_dc_date(frame: pd.DataFrame, col: str) -> pd.Series:
    """Convert ArcGIS epoch milliseconds to YYYY-MM-DD in Washington, DC."""
    if col not in frame:
        return pd.Series(pd.NaT, index=frame.index)
    return (
        pd.to_datetime(frame[col], unit="ms", utc=True, errors="coerce")
        .dt.tz_convert("America/New_York")
        .dt.date
    )


def group_report(frame: pd.DataFrame, key: str, dest: Path) -> tuple[int, int]:
    """Save duplicate-key group counts; do NOT remove any records."""
    if key not in frame:
        raise RuntimeError(f"Expected field {key!r} not present in API response")
    valid = frame[key].notna() & frame[key].astype(str).str.strip().ne("")
    counts = frame.loc[valid].groupby(key, dropna=True).size()
    duplicates = counts[counts > 1].sort_values(ascending=False)
    report = duplicates.rename("API_Record_Count").reset_index()
    report.to_csv(dest, index=False)
    return len(duplicates), int(duplicates.sum())


def main() -> None:
    RAW_DIR.mkdir(parents=True, exist_ok=True)
    AUDIT_DIR.mkdir(parents=True, exist_ok=True)

    print("=" * 75)
    print("DDOT TABLEAU | STEP 3: COMPLETE DATA DOWNLOAD + QUALITY AUDIT")
    print("=" * 75)
    print("ELIGIBILITY FILTERS APPLIED BY ARCGIS:")
    print("  1. ApplicationDate >= 2025-10-01")
    print("  2. IssueDate >= 2025-10-01")
    print("  3. IssueDate <  2026-10-01")
    print("  4. PermitTypeDescription = 'New'")
    print("  5. StatusDescription: NOT filtered (includes later-expired permits)")
    print("NOTICE: API records are NOT the same as distinct permits.\n")

    # returnIdsOnly is not constrained by standard maxRecordCount.
    meta = api_query({"where": WHERE, "returnIdsOnly": "true"})
    object_id_field = meta.get("objectIdFieldName") or "OBJECTID"
    object_ids = sorted(set(meta.get("objectIds") or []))
    if not object_ids:
        raise RuntimeError("No matching OBJECTIDs returned. Check server and filters.")

    count_response = api_query({"where": WHERE, "returnCountOnly": "true"})
    api_count = int(count_response["count"])
    print("A. NUMBER OF MATCHING API RECORDS (not deduplicated)")
    print(f"   returnCountOnly: {api_count:,}")
    print(f"   Distinct {object_id_field} from returnIdsOnly: {len(object_ids):,}")
    if api_count != len(object_ids):
        raise RuntimeError(
            "Count and OBJECTID list differ, possibly because records changed during "
            "retrieval. Rerun before interpreting results."
        )

    all_records: list[dict] = []
    batches = (len(object_ids) + CHUNK_SIZE - 1) // CHUNK_SIZE
    print(f"\nB. DOWNLOADING ALL MATCHING ATTRIBUTES IN {batches} BATCHES")
    for start in range(0, len(object_ids), CHUNK_SIZE):
        chunk = object_ids[start : start + CHUNK_SIZE]
        result = api_query({
            "objectIds": ",".join(map(str, chunk)),
            "where": WHERE,
            "outFields": "*",
            "returnGeometry": "false",
        })
        features = result.get("features", [])
        received = [feature["attributes"] for feature in features]
        got_ids = [item.get(object_id_field) for item in received]
        if len(received) != len(chunk) or set(got_ids) != set(chunk):
            raise RuntimeError(
                f"Batch {start // CHUNK_SIZE + 1}: expected {len(chunk)} OBJECTIDs, "
                f"received {len(received)}; IDs do not match. No CSV saved. "
                "The source may have changed; rerun to get a consistent snapshot."
            )
        all_records.extend(received)
        batch_no = start // CHUNK_SIZE + 1
        if batch_no == 1 or batch_no % 10 == 0 or batch_no == batches:
            print(f"   Batch {batch_no}/{batches} | downloaded {len(all_records):,}/{api_count:,}", flush=True)

    df = pd.DataFrame(all_records).sort_values(object_id_field).reset_index(drop=True)
    if df[object_id_field].nunique() != len(object_ids):
        raise RuntimeError("Repeated OBJECTID found: refusing to save misleading results.")
    print(f"\nC. VALIDATION: {len(df):,} rows with {df[object_id_field].nunique():,} unique OBJECTIDs")

    # Preserve every source attribute with its original name/value in this raw export.
    raw_path = RAW_DIR / "fy2026_new_permits_all_api_records.csv"
    df.to_csv(raw_path, index=False, encoding="utf-8-sig")
    print(f"   Raw dataset saved: {raw_path}")

    report_lines: list[str] = []
    def note(msg: str = "") -> None:
        print(msg)
        report_lines.append(msg)

    note("\nD. IDENTIFIER AUDIT (NO RECORDS REMOVED)")
    note(f"   All matching API records: {len(df):,}")
    for key in ["TrackingNumber", "PermitNumber"]:
        valid_count = int(df[key].notna().sum())
        distinct_count = int(df[key].nunique(dropna=True))
        groups, group_rows = group_report(
            df, key, AUDIT_DIR / f"03_duplicate_{'tracking' if key == 'TrackingNumber' else 'permit'}_groups.csv"
        )
        note(f"   {key}: non-null rows {valid_count:,}; unique values {distinct_count:,}; "
             f"repeated-ID groups {groups:,}; rows in repeated-ID groups {group_rows:,}")

    n_track_to_many_permits = int(
        (df.groupby("TrackingNumber", dropna=True)["PermitNumber"].nunique(dropna=True) > 1).sum()
    )
    n_permit_to_many_tracks = int(
        (df.groupby("PermitNumber", dropna=True)["TrackingNumber"].nunique(dropna=True) > 1).sum()
    )
    note(f"   TrackingNumbers linked to 2+ different PermitNumbers: {n_track_to_many_permits:,}")
    note(f"   PermitNumbers linked to 2+ different TrackingNumbers: {n_permit_to_many_tracks:,}")

    core_cols = [
        "TrackingNumber", "PermitNumber", "ApplicationDate", "LastApprovalDate",
        "IssueDate", "StatusDescription", "PermitTypeDescription", "TypeDetailNames",
        "DaysToApprove", "WorkLocationWard"
    ]
    shared = [col for col in core_cols if col in df.columns]
    same_core_rows = int(df.duplicated(subset=shared, keep=False).sum())
    note(f"   Rows sharing ALL {len(shared)} core attribute values with another row: {same_core_rows:,}")
    note("   IMPORTANT: Matching attributes do not prove duplicated permits; locations or geometry may differ.")

    note("\nE. DATE QUALITY AUDIT (Washington, DC local calendar dates)")
    for key in ["ApplicationDate", "LastApprovalDate", "IssueDate"]:
        df[key + "_DC"] = local_dc_date(df, key)
        missing = int(df[key + "_DC"].isna().sum())
        note(f"   Missing/invalid {key}: {missing:,}")

    app = pd.to_datetime(df["ApplicationDate_DC"])
    approval = pd.to_datetime(df["LastApprovalDate_DC"])
    issued = pd.to_datetime(df["IssueDate_DC"])
    note(f"   Approval BEFORE application: {int((approval < app).sum()):,}")
    note(f"   Approval AFTER issue date: {int((approval > issued).sum()):,}")
    note(f"   Issue BEFORE application: {int((issued < app).sum()):,}")
    note("   These flags need investigation; no rows are excluded in Step 3.")

    note("\nF. CURRENT STATUS OF FY2026-ISSUED NEW-PERMIT API RECORDS")
    for status, count in df["StatusDescription"].fillna("[MISSING]").value_counts().items():
        note(f"   {status}: {count:,} records ({100 * count / len(df):.2f}%)")

    note("\nG. TOP 10 REPEATED TRACKING NUMBERS (for follow-up inspection)")
    duplicated = df["TrackingNumber"].value_counts(dropna=True)
    for track, count in duplicated[duplicated > 1].head(10).items():
        subgroup = df[df["TrackingNumber"] == track]
        n_permits = subgroup["PermitNumber"].nunique(dropna=True)
        n_types = subgroup["TypeDetailNames"].nunique(dropna=True)
        n_wards = subgroup["WorkLocationWard"].nunique(dropna=True)
        note(f"   TrackingNumber {track}: {count} rows | {n_permits} permit numbers | "
             f"{n_types} type-detail strings | {n_wards} wards")

    audit_path = AUDIT_DIR / "03_data_quality_summary.txt"
    audit_path.write_text(
        "DDOT TABLEAU STEP 3: ALL FY2026 NEW-PERMIT API RECORDS\n"
        "Filters: ApplicationDate >= 2025-10-01; 2025-10-01 <= IssueDate < 2026-10-01; "
        "PermitTypeDescription = 'New'; StatusDescription not filtered.\n"
        "No record deduplication has been performed.\n"
        + "\n".join(report_lines) + "\n",
        encoding="utf-8",
    )
    print(f"\nSaved quality summary: {audit_path}")
    print("\nNEXT: Review the key structure before selecting the correct permit-level unit.")
    print("No business-day metric has been calculated yet.")


if __name__ == "__main__":
    main()
