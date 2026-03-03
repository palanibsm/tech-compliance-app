"""
Compliance and EA gap analysis module.
Validates EA Tool data for missing fields, obsolete technologies,
and other governance gaps.
"""
import polars as pl

# Maps gap names to possible column name variants in the EA Tool export
EA_GAP_COLUMN_ALIASES: dict[str, list[str]] = {
    "rcsa":          ["RCSA", "RCSA ID", "rcsa", "RCSA_ID"],
    "rsk":           ["RSK", "rsk", "Risk", "Risk ID"],
    "raf":           ["RAF", "raf", "RAF ID"],
    "tech_owner":    ["Technology Owner", "Tech Owner", "technology_owner"],
    "deputy_owner":  ["Deputy Owner", "Deputy", "deputy_owner"],
    "hos":           ["HOS", "Head of Segment", "hos"],
    "custodian":     ["Application Custodian", "App Custodian", "Custodian"],
    "upgrade_plan":  ["Upgrade Plan", "Remediation Plan", "upgrade_plan"],
}

OBSOLETE_LIFECYCLE_STATUSES = [
    "obsolete", "end of life", "eol", "retired",
    "deprecated", "end of support", "eos",
]

LIFECYCLE_COL_ALIASES = [
    "Lifecycle Status", "lifecycle_status", "Lifecycle",
    "Technology Status", "Status", "Support Status",
]


def _find_col(df: pl.DataFrame, aliases: list[str]) -> str | None:
    """Return the first alias that exists as a column in df."""
    for alias in aliases:
        if alias in df.columns:
            return alias
    return None


def check_ea_gaps(ea_df: pl.DataFrame) -> pl.DataFrame:
    """
    Add boolean gap_* columns for each governance field.
    True = the field is missing/empty for that record.
    """
    gap_exprs = []

    for gap_name, aliases in EA_GAP_COLUMN_ALIASES.items():
        col_name = _find_col(ea_df, aliases)
        if col_name:
            gap_exprs.append(
                (
                    pl.col(col_name).is_null()
                    | (pl.col(col_name).cast(pl.Utf8).str.strip_chars() == "")
                ).alias(f"gap_{gap_name}")
            )

    if gap_exprs:
        return ea_df.with_columns(gap_exprs)
    return ea_df


def flag_obsolete_technologies(ea_df: pl.DataFrame) -> pl.DataFrame:
    """
    Add 'is_obsolete' boolean column based on lifecycle/status columns.
    """
    lifecycle_col = _find_col(ea_df, LIFECYCLE_COL_ALIASES)

    if not lifecycle_col:
        return ea_df.with_columns(pl.lit(False).alias("is_obsolete"))

    pattern = "|".join(OBSOLETE_LIFECYCLE_STATUSES)
    return ea_df.with_columns(
        pl.col(lifecycle_col)
        .cast(pl.Utf8)
        .str.to_lowercase()
        .str.contains(pattern)
        .alias("is_obsolete")
    )


def flag_retired_still_tagged(ea_df: pl.DataFrame) -> pl.DataFrame:
    """
    Flag technologies that are retired/obsolete but still tagged to applications.
    Requires both a lifecycle column and an application column.
    """
    lifecycle_col = _find_col(ea_df, LIFECYCLE_COL_ALIASES)
    app_col = _find_col(ea_df, ["Application Name", "application_name", "Application"])

    if not lifecycle_col or not app_col:
        return ea_df

    pattern = "|".join(OBSOLETE_LIFECYCLE_STATUSES)

    return ea_df.with_columns(
        (
            pl.col(lifecycle_col).cast(pl.Utf8).str.to_lowercase().str.contains(pattern)
            & pl.col(app_col).cast(pl.Utf8).str.strip_chars().ne("")
        ).alias("retired_still_tagged")
    )


def build_compliance_summary(ea_df: pl.DataFrame) -> dict:
    """Return a {label: count} summary of all gap and flag columns."""
    summary = {"Total Records": len(ea_df)}

    for col in ea_df.columns:
        if col.startswith("gap_"):
            label = "Missing " + col[4:].replace("_", " ").title()
            summary[label] = int(ea_df[col].sum())
        elif col == "is_obsolete":
            summary["Obsolete Technologies"] = int(ea_df[col].sum())
        elif col == "retired_still_tagged":
            summary["Retired but Still Tagged"] = int(ea_df[col].sum())

    return summary


def get_records_with_gaps(ea_df: pl.DataFrame) -> pl.DataFrame:
    """Return only rows that have at least one gap or flag."""
    flag_cols = [
        c for c in ea_df.columns
        if c.startswith("gap_") or c in ("is_obsolete", "retired_still_tagged")
    ]
    if not flag_cols:
        return ea_df.head(0)  # empty with schema

    return ea_df.filter(
        pl.any_horizontal([pl.col(c) for c in flag_cols])
    )
