"""
Sample data generator for testing the Tech Compliance Tool.
Run: python generate_sample_data.py
Produces three Excel files in the data/ folder.
"""
import random
import pandas as pd
from pathlib import Path

random.seed(42)
Path("data").mkdir(exist_ok=True)

# ── Reference data ────────────────────────────────────────────────────────────

SOFTWARE = [
    ("Apache Tomcat",         ["9.0.65", "9.0.70", "8.5.82"]),
    ("Oracle JDK",            ["11.0.17", "17.0.5", "8u351"]),
    ("Microsoft SQL Server",  ["2019", "2017", "2016"]),
    ("Red Hat JBoss",         ["7.4.3", "6.4.0"]),
    ("IBM WebSphere",         ["9.0.5", "8.5.5"]),
    ("Nginx",                 ["1.22.1", "1.20.2"]),
    ("Apache HTTP Server",    ["2.4.54", "2.4.50"]),
    ("PostgreSQL",            ["14.5", "13.8", "12.12"]),
    ("MySQL",                 ["8.0.31", "5.7.40"]),
    ("Python",                ["3.10.8", "3.9.15", "3.8.16"]),
    ("Node.js",               ["18.12.1", "16.18.1"]),
    ("Redis",                 ["7.0.5", "6.2.8"]),
    ("Elasticsearch",         ["8.5.1", "7.17.7"]),
    ("OpenSSL",               ["3.0.7", "1.1.1s"]),
    ("VMware Tools",          ["12.1.0", "11.3.5"]),
    ("Oracle WebLogic",       ["14.1.1", "12.2.1.4"]),
    ("HAProxy",               ["2.6.6", "2.4.20"]),
    ("Splunk",                ["9.0.2", "8.2.7"]),
    ("Java Runtime Environment", ["11.0.17", "8.0.352"]),
    ("Spring Framework",      ["5.3.23", "5.2.22"]),
]

# Software that should be filtered out during cleaning
NOISE_SOFTWARE = [
    ("KB5020030",             ["N/A"]),
    ("KB4562830",             ["N/A"]),
    ("Windows Security Update", ["2022-11"]),
    ("Cumulative Update for Windows", ["2022-10"]),
    ("McAfee Agent",          ["5.7.6"]),
    ("Microsoft Hotfix",      ["KB123456"]),
]

APPLICATIONS = [
    "Core Banking System",
    "Internet Banking Portal",
    "Trade Finance Platform",
    "Risk Management System",
    "HR Management System",
    "Treasury Management",
    "Customer Onboarding",
    "Payment Gateway",
    "Reporting & Analytics",
    "Document Management",
]

OWNERS = [
    "Alice Tan", "Bob Lim", "Carol Wong",
    "David Ng", "Eve Chen", "Frank Ong",
]

# ── 1. Device42 feed (3 tabs, ~500 rows total) ────────────────────────────────

def make_hostname(prefix, n):
    return f"{prefix}{str(n).zfill(4)}"

hostnames = (
    [make_hostname("P", i) for i in range(1, 81)] +   # P = Production
    [make_hostname("D", i) for i in range(1, 21)] +   # D = DR
    [make_hostname("U", i) for i in range(1, 11)] +   # U = UAT (should be filtered out)
    [make_hostname("T", i) for i in range(1, 6)]      # T = Test  (should be filtered out)
)

def build_device42_tab(host_subset, include_noise=True):
    rows = []
    for hostname in host_subset:
        # 3–8 software per host
        for sw_name, versions in random.choices(SOFTWARE, k=random.randint(3, 8)):
            rows.append({
                "Hostname":         hostname,
                "Software Name":    sw_name,
                "Software Version": random.choice(versions),
            })
        # Sprinkle in noise entries
        if include_noise and random.random() < 0.4:
            sw_name, versions = random.choice(NOISE_SOFTWARE)
            rows.append({
                "Hostname":         hostname,
                "Software Name":    sw_name,
                "Software Version": random.choice(versions),
            })
    return pd.DataFrame(rows)

tab1 = build_device42_tab(hostnames[:40])
tab2 = build_device42_tab(hostnames[40:80])
tab3 = build_device42_tab(hostnames[80:])

with pd.ExcelWriter("data/device42_sample.xlsx", engine="openpyxl") as writer:
    tab1.to_excel(writer, sheet_name="SG_Servers", index=False)
    tab2.to_excel(writer, sheet_name="MY_Servers", index=False)
    tab3.to_excel(writer, sheet_name="Other_Servers", index=False)

print(f"✅ device42_sample.xlsx — {len(tab1)+len(tab2)+len(tab3):,} rows across 3 tabs")

# ── 2. Asset Inventory ────────────────────────────────────────────────────────

asset_rows = []
prod_hosts = [make_hostname("P", i) for i in range(1, 81)]
dr_hosts   = [make_hostname("D", i) for i in range(1, 21)]
uat_hosts  = [make_hostname("U", i) for i in range(1, 11)]

for hostname in prod_hosts:
    asset_rows.append({
        "Hostname":          hostname,
        "Application Name":  random.choice(APPLICATIONS),
        "Environment":       "PROD",
        "Status":            "LIVE",
        "Application Owner": random.choice(OWNERS),
        "Infra Entity":      random.choice(["SG-DC01", "MY-DC02", "SG-DC03"]),
    })
for hostname in dr_hosts:
    asset_rows.append({
        "Hostname":          hostname,
        "Application Name":  random.choice(APPLICATIONS),
        "Environment":       "DR",
        "Status":            "LIVE",
        "Application Owner": random.choice(OWNERS),
        "Infra Entity":      random.choice(["SG-DR01", "MY-DR01"]),
    })
# UAT entries — should be excluded by the scope filter
for hostname in uat_hosts:
    asset_rows.append({
        "Hostname":          hostname,
        "Application Name":  random.choice(APPLICATIONS),
        "Environment":       "UAT",
        "Status":            "LIVE",
        "Application Owner": random.choice(OWNERS),
        "Infra Entity":      "SG-UAT01",
    })

asset_df = pd.DataFrame(asset_rows)
asset_df.to_excel("data/asset_inventory_sample.xlsx", index=False)
print(f"✅ asset_inventory_sample.xlsx — {len(asset_df):,} rows "
      f"({len(prod_hosts)} PROD + {len(dr_hosts)} DR + {len(uat_hosts)} UAT)")

# ── 3. EA Tool Export (3 sheets) ─────────────────────────────────────────────

# Sheet 1: EA master — technology + application + lifecycle + governance fields
ea_master_rows = []
for sw_name, versions in SOFTWARE:
    for app in random.choices(APPLICATIONS, k=random.randint(1, 3)):
        ea_master_rows.append({
            "Technology Name":      sw_name,
            "Version":              random.choice(versions),
            "Application Name":     app,
            "Lifecycle Status":     random.choice([
                "Active", "Active", "Active",
                "End of Life", "Obsolete", "Deprecated",
            ]),
            "Technology Owner":     random.choice(OWNERS + [None, None]),
            "Deputy Owner":         random.choice(OWNERS + [None, None, None]),
            "HOS":                  random.choice(OWNERS + [None, None]),
            "Application Custodian": random.choice(OWNERS + [None, None]),
            "RCSA":                 random.choice(["RCSA-001", "RCSA-002", None, None, None]),
            "RSK":                  random.choice(["RSK-10", "RSK-20", None, None]),
            "RAF":                  random.choice(["RAF-A", "RAF-B", None, None]),
            "Upgrade Plan":         random.choice(["Q1 2025", "Q2 2025", None, None, None]),
        })
ea_master_df = pd.DataFrame(ea_master_rows)

# Sheet 2: Technologies not tagged to any application (deliberate subset)
untagged_rows = [
    {"Technology Name": "Redis",        "Version": "6.2.8",  "Note": "No app mapping found"},
    {"Technology Name": "HAProxy",      "Version": "2.6.6",  "Note": "No app mapping found"},
    {"Technology Name": "Splunk",       "Version": "9.0.2",  "Note": "No app mapping found"},
    {"Technology Name": "Spring Framework", "Version": "5.3.23", "Note": "No app mapping found"},
]
untagged_df = pd.DataFrame(untagged_rows)

# Sheet 3: Technology-Application discrepancies
discrepancy_rows = [
    {
        "Technology Name":   "Apache Tomcat",
        "EA Version":        "9.0.65",
        "Discovered Version": "9.0.70",
        "Discrepancy":       "Version mismatch",
        "Application":       "Core Banking System",
    },
    {
        "Technology Name":   "Oracle JDK",
        "EA Version":        "11.0.17",
        "Discovered Version": "8u351",
        "Discrepancy":       "Older version in use",
        "Application":       "Payment Gateway",
    },
    {
        "Technology Name":   "MySQL",
        "EA Version":        "8.0.31",
        "Discovered Version": "5.7.40",
        "Discrepancy":       "EOL version detected",
        "Application":       "HR Management System",
    },
]
discrepancy_df = pd.DataFrame(discrepancy_rows)

with pd.ExcelWriter("data/ea_tool_sample.xlsx", engine="openpyxl") as writer:
    ea_master_df.to_excel(writer,     sheet_name="EA Master",        index=False)
    untagged_df.to_excel(writer,      sheet_name="Untagged Techs",   index=False)
    discrepancy_df.to_excel(writer,   sheet_name="Discrepancies",    index=False)

print(f"✅ ea_tool_sample.xlsx — 3 sheets "
      f"(EA Master: {len(ea_master_df)} rows, "
      f"Untagged: {len(untagged_df)} rows, "
      f"Discrepancies: {len(discrepancy_df)} rows)")

print()
print("Sample files are in the data/ folder.")
print("Run the app:  streamlit run app.py")
