"""
Application mapping module.
Maps technologies found in Device42 to their applications via Asset Inventory.
Primary use case: identify which applications own technologies that are
not yet tagged in the EA Tool.
"""
import polars as pl


def map_hostnames_to_apps(
    tech_df: pl.DataFrame,
    asset_df: pl.DataFrame,
) -> pl.DataFrame:
    """
    Left-join tech_df with asset_df on hostname (case-insensitive).
    Result contains all tech columns + application_name, environment,
    status, application_owner from Asset Inventory.
    """
    # Normalise hostnames for joining without mutating original columns
    tech_keyed = tech_df.with_columns(
        pl.col("hostname").str.to_uppercase().alias("_hkey")
    )
    asset_keyed = asset_df.with_columns(
        pl.col("hostname").str.to_uppercase().alias("_hkey")
    ).drop("hostname")  # prevent duplicate hostname column after join

    result = tech_keyed.join(asset_keyed, on="_hkey", how="left").drop("_hkey")
    return result


def build_untagged_tech_mapping(
    untagged_tech_names: list[str],
    device42_df: pl.DataFrame,
    asset_df: pl.DataFrame,
) -> pl.DataFrame:
    """
    For technologies listed as 'not tagged to any application' in the EA Tool:
    1. Find all hostnames in Device42 that have those technologies.
    2. Look up the application for each hostname in Asset Inventory.
    3. Return a mapping: Technology → Hostname → Application

    This gives the EA team the information needed to tag technologies
    to the correct application in the EA Tool.
    """
    untagged_lower = {t.lower().strip() for t in untagged_tech_names}

    # Find Device42 records where software_name matches untagged list
    matched = device42_df.filter(
        pl.col("software_name").str.to_lowercase().str.strip_chars().is_in(untagged_lower)
    )

    if matched.is_empty():
        # Try partial match if exact yields nothing
        pattern = "|".join(
            [t.lower().strip() for t in untagged_tech_names if t.strip()]
        )
        if pattern:
            matched = device42_df.filter(
                pl.col("software_name").str.to_lowercase().str.contains(pattern)
            )

    if matched.is_empty():
        return pl.DataFrame(
            schema={
                "hostname": pl.Utf8,
                "software_name": pl.Utf8,
                "software_version": pl.Utf8,
                "application_name": pl.Utf8,
                "application_owner": pl.Utf8,
                "status": pl.Utf8,
            }
        )

    return map_hostnames_to_apps(matched, asset_df)


def summarise_app_tech_coverage(mapping_df: pl.DataFrame) -> pl.DataFrame:
    """
    Aggregate: per application, how many unique technologies and hostnames.
    """
    if "application_name" not in mapping_df.columns:
        return pl.DataFrame()

    agg_exprs = [
        pl.col("hostname").n_unique().alias("unique_hostnames"),
        pl.col("software_name").n_unique().alias("unique_technologies"),
    ]
    if "software_version" in mapping_df.columns:
        agg_exprs.append(pl.col("software_version").n_unique().alias("unique_versions"))

    return (
        mapping_df
        .group_by("application_name")
        .agg(agg_exprs)
        .sort("unique_technologies", descending=True)
    )
