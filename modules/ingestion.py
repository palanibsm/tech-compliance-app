"""
Data ingestion module.
Loads Device42, Asset Inventory, and EA Tool Excel files into Polars DataFrames.
Column names are normalized to snake_case on load.
"""
import pandas as pd
import polars as pl
from typing import Union

# ── Column name aliases → normalized name ────────────────────────────────────

DEVICE42_COL_MAP = {
    "hostname": "hostname",
    "host name": "hostname",
    "server name": "hostname",
    "device name": "hostname",
    "software name": "software_name",
    "software": "software_name",
    "product name": "software_name",
    "application name": "software_name",
    "software version": "software_version",
    "version": "software_version",
    "product version": "software_version",
}

ASSET_COL_MAP = {
    "hostname": "hostname",
    "host name": "hostname",
    "server name": "hostname",
    "application name": "application_name",
    "application": "application_name",
    "app name": "application_name",
    "environment": "environment",
    "env": "environment",
    "status": "status",
    "application owner": "application_owner",
    "app owner": "application_owner",
    "owner": "application_owner",
    "infra entity": "infra_entity",
    "infrastructure entity": "infra_entity",
    "entity": "infra_entity",
}

DEVICE42_REQUIRED = {"hostname", "software_name"}
ASSET_REQUIRED = {"hostname", "application_name"}


# ── Helpers ───────────────────────────────────────────────────────────────────

def _normalize_columns(df: pd.DataFrame, col_map: dict) -> pd.DataFrame:
    """Strip whitespace, lowercase column headers, then apply alias map."""
    df.columns = [c.strip().lower() for c in df.columns]
    return df.rename(columns={k: v for k, v in col_map.items() if k in df.columns})


def _to_polars(df: pd.DataFrame) -> pl.DataFrame:
    return pl.from_pandas(df.astype(str).fillna("").replace("nan", ""))


def _missing_cols(df: pd.DataFrame, required: set) -> set:
    return required - set(df.columns)


# ── Public loaders ────────────────────────────────────────────────────────────

def load_device42(file) -> pl.DataFrame:
    """
    Load Device42 / Infinity technology feed.
    Reads ALL tabs and concatenates them.
    Expected columns: Hostname, Software Name, Software Version
    """
    xl = pd.ExcelFile(file)
    frames = []

    for sheet in xl.sheet_names:
        try:
            raw = pd.read_excel(xl, sheet_name=sheet, dtype=str)
            raw = _normalize_columns(raw, DEVICE42_COL_MAP)
            missing = _missing_cols(raw, DEVICE42_REQUIRED)
            if missing:
                continue  # skip sheets that don't have expected columns
            keep = [c for c in ["hostname", "software_name", "software_version"] if c in raw.columns]
            frames.append(raw[keep])
        except Exception:
            continue

    if not frames:
        raise ValueError(
            "No valid Device42 data found. "
            "Ensure at least one sheet has 'Hostname' and 'Software Name' columns."
        )

    combined = pd.concat(frames, ignore_index=True)
    return _to_polars(combined)


def load_asset_inventory(file) -> pl.DataFrame:
    """
    Load Asset Inventory from Infinity.
    Applies required filters:
      - Infra Entity contains 'SG' or 'MY'
      - Environment in ['PROD', 'DR']
      - Status = 'LIVE'
    """
    xl = pd.ExcelFile(file)
    raw = pd.read_excel(xl, sheet_name=0, dtype=str)
    raw = _normalize_columns(raw, ASSET_COL_MAP)

    missing = _missing_cols(raw, ASSET_REQUIRED)
    if missing:
        raise ValueError(f"Asset Inventory is missing required columns: {missing}")

    # Apply scope filters
    if "infra_entity" in raw.columns:
        raw = raw[raw["infra_entity"].str.upper().str.contains("SG|MY", na=False)]
    if "environment" in raw.columns:
        raw = raw[raw["environment"].str.strip().str.upper().isin(["PROD", "DR"])]
    if "status" in raw.columns:
        raw = raw[raw["status"].str.strip().str.upper() == "LIVE"]

    return _to_polars(raw)


def load_ea_tool(file) -> dict[str, pl.DataFrame]:
    """
    Load EA Tool Excel export.
    Returns a dict of {sheet_name: DataFrame} — the user selects which
    sheet to use for matching and compliance checks.
    """
    xl = pd.ExcelFile(file)
    sheets = {}

    for sheet in xl.sheet_names:
        try:
            raw = pd.read_excel(xl, sheet_name=sheet, dtype=str)
            raw.columns = [c.strip() for c in raw.columns]
            sheets[sheet] = _to_polars(raw)
        except Exception:
            continue

    if not sheets:
        raise ValueError("No readable sheets found in EA Tool file.")

    return sheets
