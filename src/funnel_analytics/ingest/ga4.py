"""Load session-level files exported from BigQuery (sql/bigquery/01_session_funnel.sql)."""
from __future__ import annotations

from pathlib import Path

import duckdb

from ..config import GA4_EXPORT_DIR

EXPECTED_COLUMNS = {
    "session_id", "session_date", "ga_session_number", "session_source", "session_medium",
    "user_source", "user_medium", "device_category", "country", "pageviews",
    "engagement_sec", "has_view_item", "has_add_to_cart", "has_begin_checkout",
    "has_purchase", "transactions", "purchase_revenue_usd",
}


def export_files(folder: Path = GA4_EXPORT_DIR) -> list[Path]:
    if not folder.exists():
        return []
    return sorted(
        p for p in folder.iterdir()
        if p.suffix.lower() in {".csv", ".parquet"} or p.name.lower().endswith(".csv.gz")
    )


def load_raw(con: duckdb.DuckDBPyConnection, folder: Path = GA4_EXPORT_DIR) -> int:
    """Load every export file into raw_ga4. Returns the row count, or 0 if there are no files."""
    files = export_files(folder)
    if not files:
        con.execute("DROP TABLE IF EXISTS raw_ga4")
        return 0
    csvs = [str(p) for p in files if p.suffix.lower() != ".parquet"]
    parquets = [str(p) for p in files if p.suffix.lower() == ".parquet"]
    parts = []
    if csvs:
        parts.append(f"SELECT * FROM read_csv({csvs!r}, header = true, union_by_name = true)")
    if parquets:
        parts.append(f"SELECT * FROM read_parquet({parquets!r}, union_by_name = true)")
    con.execute(f"CREATE OR REPLACE TABLE raw_ga4 AS {' UNION ALL BY NAME '.join(parts)}")

    cols = {r[0] for r in con.execute("DESCRIBE raw_ga4").fetchall()}
    missing = EXPECTED_COLUMNS - cols
    if missing:
        raise ValueError(
            f"GA4 export is missing columns {sorted(missing)}. "
            "Re-run sql/bigquery/01_session_funnel.sql unchanged."
        )
    # Drop duplicate sessions if the export was split into overlapping files.
    con.execute(
        "CREATE OR REPLACE TABLE raw_ga4 AS SELECT * FROM raw_ga4 "
        "QUALIFY row_number() OVER (PARTITION BY session_id ORDER BY session_date) = 1"
    )
    return con.execute("SELECT COUNT(*) FROM raw_ga4").fetchone()[0]
