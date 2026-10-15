#%%
# PURPOSE:
# Conduct an initial exploration of the DDOT Construction Permit
# ArcGIS REST API to understand the available data and its structure.
# Retrieve sample records, inspect key attributes, and examine
# application, approval, and issue dates. This preliminary exploration
# helps identify relevant fields for the subsequent analysis.
#
# OUTPUT: Displays sample records and field names in the console.

import requests
import pandas as pd

# Official DDOT ArcGIS REST API
url = (
    "https://maps2.dcgis.dc.gov/dcgis/rest/services/"
    "DCGIS_APPS/DDOT_TOPS/MapServer/23/query"
)

# Request a sample of 10 permits
params = {
    "where": "1=1",
    "outFields": (
        "TrackingNumber,PermitNumber,ApplicationDate,"
        "LastApprovalDate,IssueDate,StatusDescription,"
        "PermitTypeDescription,TypeDetailNames,FiscalYear"
    ),
    "returnGeometry": "false",
    "resultRecordCount": 10,
    "f": "json"
}

response = requests.get(url, params=params, timeout=60)
response.raise_for_status()
data = response.json()

if "error" in data:
    raise RuntimeError(data["error"])

df = pd.DataFrame(
    [item["attributes"] for item in data["features"]]
)

# Convert dates to readable format
for col in ["ApplicationDate", "LastApprovalDate", "IssueDate"]:
    df[col] = pd.to_datetime(
        df[col], unit="ms", errors="coerce"
    ).dt.date

print("Number of sample records:", len(df))
print("\nColumns:")
print(df.columns.tolist())
print("\nSample data:")
print(df.to_string(index=False))
