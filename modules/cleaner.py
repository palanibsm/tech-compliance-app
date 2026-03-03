"""
Data cleaning module.
Filters hostnames, removes non-core software entries, deduplicates,
and adds a normalised tech_key for matching.
"""
import polars as pl
from config import HOSTNAME_PREFIXES, EXCLUDE_PATTERNS


def filter_hostnames(df: pl.DataFrame, hostname_col: str = "hostname") -> pl.DataFrame:
    """Keep only hostnames starting with P or D (case-insensitive)."""
    prefix_pattern = "^[" + "".join(HOSTNAME_PREFIXES).upper() + "]"
    return df.filter(
        pl.col(hostname_col).str.to_uppercase().str.contains(prefix_pattern)
    )


def remove_excluded_software(df: pl.DataFrame, software_col: str = "software_name") -> pl.DataFrame:
    """
    Remove KB patches, hotfixes, agents, and other non-core software entries.
    Patterns are defined in config.EXCLUDE_PATTERNS.
    """
    combined = "|".join(EXCLUDE_PATTERNS)
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


def clean_device42(df: pl.DataFrame) -> pl.DataFrame:
    """
    Full cleaning pipeline for Device42 data:
    1. Filter to P/D hostnames
    2. Remove excluded software
    3. Deduplicate
    4. Add tech_key
    """
    df = filter_hostnames(df)
    df = remove_excluded_software(df)
    df = deduplicate(df)
    df = add_tech_key(df)
    return df


def get_cleaning_stats(raw: pl.DataFrame, cleaned: pl.DataFrame) -> dict:
    """Return a summary of what was removed during cleaning."""
    return {
        "raw_records": len(raw),
        "cleaned_records": len(cleaned),
        "removed": len(raw) - len(cleaned),
        "removal_pct": round((len(raw) - len(cleaned)) / max(len(raw), 1) * 100, 1),
        "unique_hostnames": cleaned["hostname"].n_unique() if "hostname" in cleaned.columns else 0,
        "unique_technologies": cleaned["software_name"].n_unique() if "software_name" in cleaned.columns else 0,
    }
