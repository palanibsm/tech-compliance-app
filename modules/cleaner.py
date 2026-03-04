"""
Data cleaning module.
Filters hostnames, removes non-core software entries, deduplicates,
and adds a normalised tech_key for matching.

All functions accept explicit rule parameters so the UI can override
the defaults from config without modifying any files.
"""
import polars as pl
from config import HOSTNAME_PREFIXES, EXCLUDE_PATTERNS


def filter_hostnames(
    df: pl.DataFrame,
    prefixes: list[str] | None = None,
    hostname_col: str = "hostname",
) -> pl.DataFrame:
    """Keep only hostnames whose first character matches one of `prefixes`."""
    if prefixes is None:
        prefixes = list(HOSTNAME_PREFIXES)
    chars = "".join(p[0].upper() for p in prefixes if p.strip())
    pattern = f"^[{chars}]"
    return df.filter(
        pl.col(hostname_col).str.to_uppercase().str.contains(pattern)
    )


def remove_excluded_software(
    df: pl.DataFrame,
    patterns: list[str] | None = None,
    software_col: str = "software_name",
) -> pl.DataFrame:
    """Remove rows whose software name matches any of `patterns` (regex, case-insensitive)."""
    if patterns is None:
        patterns = EXCLUDE_PATTERNS
    active = [p.strip() for p in patterns if p.strip()]
    if not active:
        return df
    combined = "|".join(active)
    return df.filter(
        ~pl.col(software_col).str.to_lowercase().str.contains(combined)
    )


def deduplicate(df: pl.DataFrame) -> pl.DataFrame:
    """Remove exact duplicate rows."""
    return df.unique()


def add_tech_key(
    df: pl.DataFrame,
    name_col: str = "software_name",
    ver_col: str = "software_version",
) -> pl.DataFrame:
    """
    Add a normalised 'tech_key' column: lowercase(software_name + ' ' + version).
    Used as the primary key for matching.
    """
    if ver_col in df.columns:
        return df.with_columns(
            (
                pl.col(name_col).str.strip_chars().str.to_lowercase()
                + pl.lit(" ")
                + pl.col(ver_col).str.strip_chars().str.to_lowercase()
            )
            .str.strip_chars()
            .alias("tech_key")
        )
    return df.with_columns(
        pl.col(name_col).str.strip_chars().str.to_lowercase().alias("tech_key")
    )


def clean_device42(
    df: pl.DataFrame,
    hostname_prefixes: list[str] | None = None,
    exclude_patterns: list[str] | None = None,
) -> tuple[pl.DataFrame, dict]:
    """
    Full cleaning pipeline for Device42 data.
    Returns (cleaned_df, step_stats) so the UI can show per-step row counts.

    Steps:
      1. Filter to allowed hostname prefixes
      2. Remove excluded software patterns
      3. Deduplicate
      4. Add tech_key
    """
    stats = {"raw": len(df)}

    df = filter_hostnames(df, prefixes=hostname_prefixes)
    stats["after_hostname_filter"] = len(df)

    df = remove_excluded_software(df, patterns=exclude_patterns)
    stats["after_software_filter"] = len(df)

    df = deduplicate(df)
    stats["after_dedup"] = len(df)

    df = add_tech_key(df)
    stats["unique_hostnames"]    = df["hostname"].n_unique() if "hostname" in df.columns else 0
    stats["unique_technologies"] = df["software_name"].n_unique() if "software_name" in df.columns else 0

    return df, stats
