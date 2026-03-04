# Technology Version Compliance & Obsolescence Management Tool

A local Python application for managing technology lifecycle compliance across enterprise servers.
Runs entirely on a laptop — no server, no cloud deployment required. Makes API calls to **Azure OpenAI** only for ambiguous technology name matching.

---

## Table of Contents

1. [Purpose](#purpose)
2. [Architecture](#architecture)
3. [Tech Stack](#tech-stack)
4. [Folder Structure](#folder-structure)
5. [Installation & Setup](#installation--setup)
6. [Input File Requirements](#input-file-requirements)
7. [Workflow & Data Flow](#workflow--data-flow)
8. [Step-by-Step Guide](#step-by-step-guide)
9. [Azure AI Configuration](#azure-ai-configuration)

---

## Purpose

This tool addresses a common enterprise governance challenge:

> *"Which technologies are running on our servers — are they registered in our EA Tool, are they tagged to the right applications, and are any of them obsolete?"*

It takes three data sources as input, reconciles them, flags compliance gaps, and produces audit-ready Excel reports.

---

## Architecture

```
┌──────────────────────────────────────────────────────────────────┐
│                      User's Laptop                               │
│                                                                  │
│  ┌────────────────────────────────────────────────────────────┐  │
│  │                  Streamlit Web UI                          │  │
│  │              (browser at localhost:8501)                   │  │
│  │                                                            │  │
│  │  Sidebar Navigation          Main Content Area            │  │
│  │  ─────────────────           ──────────────────────────   │  │
│  │  ✅ Step 1: Upload     ───►  Step content + Next/Back     │  │
│  │  ✅ Step 2: Clean             buttons                      │  │
│  │  ⏳ Step 3: Match                                          │  │
│  │  ⏳ Step 4: Map                                            │  │
│  │  ⏳ Step 5: Compliance                                     │  │
│  │  ⏳ Step 6: Reports                                        │  │
│  └────────────────────────────────────────────────────────────┘  │
│                           │                                      │
│            ┌──────────────┼──────────────┐                       │
│            ▼              ▼              ▼                       │
│      ┌──────────┐  ┌──────────┐  ┌──────────┐                   │
│      │Ingestion │  │Processing│  │Reporting │                   │
│      │  Module  │  │ Modules  │  │  Module  │                   │
│      └──────────┘  └──────────┘  └──────────┘                   │
│                           │                                      │
│                    ┌──────▼──────┐                               │
│                    │   DuckDB    │                               │
│                    │ (in-memory) │                               │
│                    └─────────────┘                               │
└──────────────────────────────────────────────────────────────────┘
                            │
              (only for ambiguous tech matching)
                            │
                            ▼
               ┌─────────────────────────┐
               │    Azure OpenAI API     │
               │    gpt-4o-mini          │
               └─────────────────────────┘
```

---

## Tech Stack

| Layer | Library | Purpose |
|---|---|---|
| UI | `streamlit` | Browser-based local app, file uploads, progress bars, navigation |
| Data Processing | `polars` | Fast DataFrame operations on 3M+ rows |
| Local Query Engine | `duckdb` | SQL joins across large in-memory datasets |
| Fuzzy Matching | `rapidfuzz` | C-backed string similarity matching |
| AI Matching | `openai` (Azure) | LLM validation for ambiguous technology names |
| Excel Read | `pandas` | Reliable multi-tab Excel ingestion |
| Excel Write | `openpyxl` | Formatted Excel output with styles |
| Config | `python-dotenv` | Load Azure credentials from `.env` file |

---

## Folder Structure

```
tech-compliance-app/
│
├── app.py                   ← Main Streamlit application (UI + step router)
├── config.py                ← Azure AI config + matching thresholds
├── requirements.txt         ← All pip dependencies
├── run.bat                  ← Double-click launcher for Windows
├── .env.example             ← Azure credentials template
├── generate_sample_data.py  ← Generates mock Excel files for testing
│
├── modules/
│   ├── ingestion.py         ← Load Excel files, normalize column names
│   ├── cleaner.py           ← Filter, deduplicate, standardize data
│   ├── matcher.py           ← 3-tier technology matching engine
│   ├── mapper.py            ← Map technologies to applications
│   ├── compliance.py        ← EA gap analysis and obsolescence flagging
│   └── reporter.py          ← Generate formatted Excel reports
│
├── db/
│   └── store.py             ← DuckDB in-memory session management
│
├── data/                    ← Drop input Excel files here (gitignored)
└── output/                  ← Generated reports saved here (gitignored)
```

---

## Installation & Setup

### On the development / office laptop

```bash
# 1. Clone or download the repository
git clone https://github.com/palanibsm/tech-compliance-app.git
cd tech-compliance-app

# 2. Install dependencies (one time only)
pip install -r requirements.txt

# 3. (Optional) Configure Azure AI credentials
copy .env.example .env
# Edit .env and fill in your Azure OpenAI endpoint and key

# 4. (Optional) Generate sample test data
python generate_sample_data.py

# 5. Launch the app
streamlit run app.py
#    OR simply double-click run.bat
```

The app opens automatically in your default browser at `http://localhost:8501`.

---

## Input File Requirements

### 1. Device42 / Infinity Feed (Technology Discovery)

- **Format:** Excel `.xlsx` — can have multiple tabs
- **Scope:** All servers; the app filters to P/D hostnames automatically
- **Required columns** (exact names or common variants accepted):

| Required Column | Accepted Variants |
|---|---|
| `Hostname` | Host Name, Server Name, Device Name |
| `Software` | Software Name, Product Name |
| `Version` | Software Version, Product Version |

---

### 2. Asset Inventory (Infinity)

- **Format:** Excel `.xlsx` — single sheet
- **Scope filter applied automatically:** Infra Entity contains SG or MY · Environment = PROD or DR · Status = LIVE
- **Required columns:**

| Required Column | Accepted Variants |
|---|---|
| `Host Name` | Hostname, Server Name |
| `Application Name` | Application, App Name |
| `Environment` | Env |
| `Status` | — |
| `Application Owner` | App Owner, Owner |
| `Infra Entity` | Infrastructure Entity, Entity |

---

### 3. EA Tool Export (HOPEX / TA Export)

- **Format:** Excel `.xlsx` — multiple sheets expected:

| Sheet | Purpose |
|---|---|
| EA Master | Full technology–application mapping with lifecycle and governance fields |
| Untagged Techs | Technologies not yet tagged to any application |
| Discrepancies | Version mismatches between EA Tool and discovered data |

- Column names are read as-is; the app lets you select which column to use at each step.

---

## Workflow & Data Flow

```
 ┌─────────────────┐   ┌──────────────────┐   ┌──────────────────────┐
 │  Device42 Feed  │   │ Asset Inventory  │   │   EA Tool Export     │
 │  (multi-tab     │   │ (filtered:       │   │   (HOPEX/TA Export)  │
 │   ~3M rows)     │   │  SG/MY,PROD/DR,  │   │                      │
 │                 │   │  LIVE only)      │   │                      │
 └────────┬────────┘   └────────┬─────────┘   └──────────┬───────────┘
          │                     │                         │
          ▼                     ▼                         ▼
 ┌────────────────────────────────────────────────────────────────────┐
 │  STEP 1: UPLOAD                                                    │
 │  • Load all Excel files into memory                                │
 │  • Normalize column names (handle variants like "Host Name" etc.)  │
 │  • Apply Asset Inventory scope filter (SG/MY, PROD/DR, LIVE)       │
 │  • Show row counts and preview per file                            │
 └────────────────────────────────┬───────────────────────────────────┘
                                  │
                                  ▼
 ┌────────────────────────────────────────────────────────────────────┐
 │  STEP 2: PROCESS & CLEAN (Device42 data only)                      │
 │                                                                    │
 │  User-editable rules:                                              │
 │  ┌─────────────────────────────────────────────────────────────┐   │
 │  │ Rule 1 — Hostname filter                                    │   │
 │  │   Keep only hostnames starting with P or D                  │   │
 │  │   (Production and DR servers; excludes UAT, Test, etc.)     │   │
 │  │                                                             │   │
 │  │ Rule 2 — Software exclusion patterns (regex)                │   │
 │  │   Remove: KB patches, hotfixes, security/cumulative updates,│   │
 │  │   service packs, Windows Defender updates, definition updates│   │
 │  │   These are OS-level noise, not application technologies.   │   │
 │  │                                                             │   │
 │  │ Rule 3 — Deduplication                                      │   │
 │  │   Remove exact duplicate hostname + software + version rows │   │
 │  │                                                             │   │
 │  │ Rule 4 — tech_key generation (internal)                     │   │
 │  │   Creates lowercase "software + version" key for matching   │   │
 │  └─────────────────────────────────────────────────────────────┘   │
 │                                                                    │
 │  Output: Per-step row counts showing exactly what was removed      │
 │  Download: Technology Recon Process_MMM-YYYY.xlsx                  │
 │            Columns: Hostname | Software | Version |                │
 │                     Concatenated Technology                        │
 │            Tab: "PROD and DR from D42_MMM-YYYY"                    │
 └────────────────────────────────┬───────────────────────────────────┘
                                  │
                                  ▼
 ┌────────────────────────────────────────────────────────────────────┐
 │  STEP 3: MATCH TECHNOLOGIES                                        │
 │                                                                    │
 │  Compares unique technology names from Device42 against the        │
 │  EA Tool technology list. Three tiers:                             │
 │                                                                    │
 │  Tier 1 — Exact Match (instant)                                    │
 │    Case-insensitive string equality                                │
 │    → Confidence: 100%  Action: auto-accept                         │
 │                                                                    │
 │  Tier 2 — Fuzzy Match (RapidFuzz, fast)                            │
 │    Token sort ratio algorithm handles word order differences,      │
 │    abbreviations, minor naming variations                          │
 │    Score ≥ 85  → auto-accept                                       │
 │    Score 60–84 → escalate to Tier 3                                │
 │    Score < 60  → no match                                          │
 │                                                                    │
 │  Tier 3 — AI Match (Azure OpenAI, only for ambiguous cases)        │
 │    Sends the pair to gpt-4o-mini with a structured prompt          │
 │    Returns: match true/false, confidence score, reason             │
 │    → Minimises API cost: only ~5–15% of records reach this tier    │
 │                                                                    │
 │  Output: Match results table with Unmatched list for human review  │
 └────────────────────────────────┬───────────────────────────────────┘
                                  │
                                  ▼
 ┌────────────────────────────────────────────────────────────────────┐
 │  STEP 4: MAP APPLICATIONS                                          │
 │                                                                    │
 │  Section A — Full Technology → Application Mapping                 │
 │    Join cleaned Device42 data with Asset Inventory on Hostname     │
 │    (case-insensitive). Result: every technology row gains          │
 │    Application Name, Application Owner, Environment, Status.       │
 │                                                                    │
 │  Section B — Find Applications for EA Untagged Technologies        │
 │    Takes the "not tagged" list from EA Tool.                       │
 │    Finds all Device42 hostnames using those technologies.          │
 │    Looks up the application for each hostname in Asset Inventory.  │
 │    Result: Technology X → used by Hostname Y → owned by App Z      │
 │    → EA team can now tag the technology to the correct application │
 └────────────────────────────────┬───────────────────────────────────┘
                                  │
                                  ▼
 ┌────────────────────────────────────────────────────────────────────┐
 │  STEP 5: COMPLIANCE CHECK                                          │
 │                                                                    │
 │  Scans the EA Tool master export and flags:                        │
 │                                                                    │
 │  Governance Gaps (gap_* columns added as True/False):              │
 │    • Missing RCSA                                                  │
 │    • Missing RSK / RAF                                             │
 │    • Missing Technology Owner / Deputy / HOS                       │
 │    • Missing Application Custodian                                 │
 │    • Missing Upgrade / Remediation Plan                            │
 │                                                                    │
 │  Lifecycle Flags:                                                  │
 │    • is_obsolete: lifecycle status = Obsolete / EOL / Deprecated / │
 │                   End of Life / End of Support / Retired           │
 │    • retired_still_tagged: technology is retired but still linked  │
 │                             to an active application               │
 │                                                                    │
 │  Output: Summary metrics + filterable tables per flag type         │
 └────────────────────────────────┬───────────────────────────────────┘
                                  │
                                  ▼
 ┌────────────────────────────────────────────────────────────────────┐
 │  STEP 6: REPORTS                                                   │
 │                                                                    │
 │  Generates a single Excel workbook containing all completed steps: │
 │    • Tech Recon        — cleaned Device42 data                     │
 │    • App Mapping       — technology → application join             │
 │    • Compliance Gaps   — EA data with gap/obsolete flags           │
 │    • Match Results     — technology matching outcomes              │
 │    • Untagged Tech Mapping — untagged tech → owning application    │
 │                                                                    │
 │  Large sheets (>1,048,575 rows) are auto-split into Pt 1, Pt 2…   │
 │  Gap/obsolete cells are highlighted in red for easy review.        │
 └────────────────────────────────────────────────────────────────────┘
```

---

## Step-by-Step Guide

### Step 1 — Upload Data
Upload all three Excel files. Files are only re-processed if you upload a different file — switching between steps does not trigger reloading. The Device42 feed shows a per-tab progress bar since it can contain 3M+ rows across multiple sheets.

### Step 2 — Process & Clean
Review and optionally edit the cleaning rules before running:
- **Hostname Prefixes** — default `P, D`. Add more letters if needed (e.g. `P, D, S`).
- **Exclusion Patterns** — regex patterns, one per line. Add your own to exclude vendor-specific agents or patch entries unique to your environment.

After running, a breakdown table shows exactly how many rows each rule removed. Download the cleaned file as `Technology Recon Process_MMM-YYYY.xlsx`.

### Step 3 — Match Technologies
Select which EA Tool sheet contains the technology list and which column holds the technology name. The matching engine runs automatically across three tiers. Review the **Unmatched** tab — these are technologies in Device42 with no equivalent in the EA Tool and need manual investigation.

### Step 4 — Map Applications
**Section A** gives you the full picture of which application owns which technology via hostname.
**Section B** is the key remediation workflow: select the EA "Untagged Techs" sheet, and the tool tells you which application to tag each technology to in the EA Tool.

### Step 5 — Compliance Check
Select the EA Master sheet. The tool scans every row and adds boolean flag columns. The **Records with Gaps** tab shows only rows that have at least one issue — use this as the action list for the EA team.

### Step 6 — Reports
Click **Generate Excel Report** to download a consolidated workbook containing all outputs from the completed steps. Share this with stakeholders or attach to your governance audit.

---

## Azure AI Configuration

Azure AI is **optional** — the app works fully without it (fuzzy matching only). It is used exclusively for technology name pairs where fuzzy matching scores between 60–84%, typically 5–15% of all comparisons.

**To enable:**

1. Copy `.env.example` to `.env`:
   ```
   AZURE_OPENAI_ENDPOINT=https://your-resource.openai.azure.com
   AZURE_OPENAI_API_KEY=your-api-key-here
   AZURE_OPENAI_DEPLOYMENT=gpt-4o-mini
   ```
2. Restart the app — credentials load automatically.
3. Alternatively, enter them directly in the sidebar without editing any files.

**Cost note:** For a typical 3M-row dataset with ~20,000 unique technologies, expect fewer than 3,000 AI calls (ambiguous pairs only). At gpt-4o-mini pricing this is negligible.

---

## Sample Data for Testing

Generate realistic mock Excel files to test the full workflow before using real data:

```bash
python generate_sample_data.py
```

This creates three files in the `data/` folder:
- `device42_sample.xlsx` — 3 tabs, ~500 rows including KB patches and noise entries to filter
- `asset_inventory_sample.xlsx` — PROD + DR + UAT rows (UAT gets filtered out automatically)
- `ea_tool_sample.xlsx` — 3 sheets: EA Master, Untagged Techs, Discrepancies
