"""DuckDB warehouse: raw → staging → fct_sessions → marts, plus data-quality checks."""
from __future__ import annotations

from pathlib import Path

import duckdb
import pandas as pd

from .config import MARTS_DIR, SQL_DIR, WAREHOUSE_PATH

GA4_LAYOUT_SOURCES = {"ga4": "raw_ga4", "demo": "raw_demo"}

STG_COLUMNS = (
    "dataset, session_id, session_date, month_sort, month_label, channel, device, region, "
    "visitor_type, is_weekend, pageviews, engagement_sec, s_view, s_cart, s_checkout, "
    "s_purchase, transactions, revenue"
)


def connect(path: Path = WAREHOUSE_PATH, read_only: bool = False) -> duckdb.DuckDBPyConnection:
    path.parent.mkdir(parents=True, exist_ok=True)
    return duckdb.connect(str(path), read_only=read_only)


def table_exists(con, name: str) -> bool:
    return bool(
        con.execute(
            "SELECT COUNT(*) FROM information_schema.tables WHERE table_name = ?", [name]
        ).fetchone()[0]
    )


def _run_sql_file(con, name: str, **params: str) -> None:
    sql = (SQL_DIR / name).read_text()
    con.execute(sql.format(**params) if params else sql)


def build_models(con) -> list[str]:
    """Build staging, fact and mart tables from whichever raw tables are present."""
    _run_sql_file(con, "00_macros.sql")
    staged = []
    if table_exists(con, "raw_uci"):
        _run_sql_file(con, "10_stg_uci.sql")
        con.execute("CREATE OR REPLACE TABLE uci_features AS SELECT * FROM raw_uci")
        staged.append("uci")
    for key, raw in GA4_LAYOUT_SOURCES.items():
        if table_exists(con, raw):
            _run_sql_file(con, "20_stg_ga4.sql", dataset=key, source=raw)
            staged.append(key)
        else:
            con.execute(f"DROP TABLE IF EXISTS stg_{key}")
    if not staged:
        raise RuntimeError("No raw data loaded: run the pipeline first.")

    union = " UNION ALL ".join(f"SELECT {STG_COLUMNS} FROM stg_{k}" for k in staged)
    # Closed-funnel flags: a step counts only if every earlier *observable* step
    # was also reached. Unobservable steps (NULL for the whole dataset) are skipped.
    con.execute(
        f"""
        CREATE OR REPLACE TABLE fct_sessions AS
        WITH u AS ({union})
        SELECT
            *,
            s_view AS c_view,
            CASE WHEN s_cart IS NULL THEN NULL ELSE s_view AND s_cart END AS c_cart,
            CASE WHEN s_checkout IS NULL THEN NULL
                 ELSE s_view AND COALESCE(s_cart, TRUE) AND s_checkout END AS c_checkout,
            s_view AND COALESCE(s_cart, TRUE) AND COALESCE(s_checkout, TRUE) AND s_purchase
                AS c_purchase
        FROM u
        """
    )
    _run_sql_file(con, "40_marts.sql")
    return staged


# --------------------------------------------------------------------------- #
# Data quality
# --------------------------------------------------------------------------- #
# (name, severity, SQL returning failing rows per dataset, description)
CHECKS = [
    (
        "unique_session_id", "error",
        "SELECT dataset, COUNT(*) - COUNT(DISTINCT session_id) FROM fct_sessions GROUP BY 1",
        "Every session appears exactly once.",
    ),
    (
        "non_negative_revenue", "error",
        "SELECT dataset, COUNT(*) FILTER (WHERE revenue < 0) FROM fct_sessions GROUP BY 1",
        "Revenue is never negative.",
    ),
    (
        "revenue_only_on_purchase", "error",
        "SELECT dataset, COUNT(*) FILTER (WHERE revenue > 0 AND NOT s_purchase) FROM fct_sessions GROUP BY 1",
        "Only purchasing sessions carry revenue.",
    ),
    (
        "dimensions_not_null", "error",
        "SELECT dataset, COUNT(*) FILTER (WHERE channel IS NULL OR device IS NULL OR region IS NULL) "
        "FROM fct_sessions GROUP BY 1",
        "Channel, device and region are always filled.",
    ),
    (
        "mart_reconciles_to_fact", "error",
        "SELECT f.dataset, ABS(f.n - m.n) FROM "
        "(SELECT dataset, COUNT(*) n FROM fct_sessions GROUP BY 1) f JOIN "
        "(SELECT dataset, SUM(sessions) n FROM mart_funnel GROUP BY 1) m USING (dataset)",
        "Session totals in mart_funnel match fct_sessions.",
    ),
    (
        "purchase_without_value", "warn",
        "SELECT dataset, COUNT(*) FILTER (WHERE s_purchase AND COALESCE(revenue, 0) = 0 AND revenue IS NOT NULL) "
        "FROM fct_sessions GROUP BY 1",
        "Purchases recorded with zero revenue (obfuscation or tagging gaps).",
    ),
    (
        "funnel_leakage", "info",
        "SELECT dataset, COUNT(*) FILTER (WHERE s_purchase AND NOT c_purchase) FROM fct_sessions GROUP BY 1",
        "Purchases that skipped an earlier logged step. The open funnel counts them; the closed funnel does not.",
    ),
]


def run_quality_checks(con) -> pd.DataFrame:
    totals = dict(con.execute("SELECT dataset, COUNT(*) FROM fct_sessions GROUP BY 1").fetchall())
    rows = []
    for name, severity, sql, desc in CHECKS:
        for dataset, failing in con.execute(sql).fetchall():
            failing = int(failing or 0)
            status = "pass" if failing == 0 else ("fail" if severity == "error" else severity)
            rows.append(
                {
                    "check": name, "dataset": dataset, "severity": severity,
                    "failing_rows": failing, "total_rows": totals.get(dataset, 0),
                    "pct": failing / max(totals.get(dataset, 1), 1), "status": status,
                    "description": desc,
                }
            )
    return pd.DataFrame(rows)


def export_marts(con, out_dir: Path = MARTS_DIR) -> list[Path]:
    """Write marts to Parquet + CSV so Power BI, Excel or Looker Studio can use them too."""
    out_dir.mkdir(parents=True, exist_ok=True)
    written = []
    for table in ("mart_funnel", "mart_dataset_summary"):
        for ext, fmt in (("parquet", "PARQUET"), ("csv", "CSV, HEADER")):
            path = out_dir / f"{table}.{ext}"
            con.execute(f"COPY {table} TO '{path}' (FORMAT {fmt})")
            written.append(path)
    return written
