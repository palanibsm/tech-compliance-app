"""
DuckDB in-memory store for fast SQL queries across large datasets.
A single connection is maintained per session via module-level singleton.
"""
import duckdb
import polars as pl
from typing import Optional

_conn: Optional[duckdb.DuckDBPyConnection] = None


def get_conn() -> duckdb.DuckDBPyConnection:
    global _conn
    if _conn is None:
        _conn = duckdb.connect(":memory:")
    return _conn


def register(name: str, df: pl.DataFrame) -> None:
    """Register a Polars DataFrame as a DuckDB view."""
    conn = get_conn()
    conn.register(name, df.to_arrow())


def query(sql: str) -> pl.DataFrame:
    """Run a SQL query and return a Polars DataFrame."""
    conn = get_conn()
    return pl.from_arrow(conn.execute(sql).arrow())


def reset() -> None:
    """Close and reset the connection (called on session reset)."""
    global _conn
    if _conn:
        _conn.close()
    _conn = duckdb.connect(":memory:")
