"""End-to-end pipeline: `python -m funnel_analytics.pipeline`."""
from __future__ import annotations

import argparse
import sys
import time
from pathlib import Path

from . import warehouse
from .config import UCI_CSV, WAREHOUSE_PATH
from .ingest import ga4, simulate, uci


def run(
    demo_sessions: int = 90_000,
    skip_download: bool = False,
    export: bool = True,
    db_path: Path = WAREHOUSE_PATH,
    log=print,
) -> dict:
    t0 = time.time()
    con = warehouse.connect(db_path)
    counts = {}
    try:
        if not skip_download or not UCI_CSV.exists():
            try:
                uci.download()
            except Exception as exc:  # network down: carry on with what we have
                log(f"[uci] download failed ({exc}); skipping UCI")
        if UCI_CSV.exists():
            counts["uci"] = uci.load_raw(con)
            log(f"[uci] loaded {counts['uci']:,} sessions")

        counts["ga4"] = ga4.load_raw(con)
        log(
            f"[ga4] loaded {counts['ga4']:,} sessions from data/raw/ga4/"
            if counts["ga4"]
            else "[ga4] no BigQuery export found in data/raw/ga4/ (see sql/bigquery/)"
        )

        if demo_sessions > 0:
            counts["demo"] = simulate.load_raw(con, demo_sessions)
            log(f"[demo] simulated {counts['demo']:,} GA4-schema sessions")
        else:
            con.execute("DROP TABLE IF EXISTS raw_demo")

        staged = warehouse.build_models(con)
        log(f"[models] built staging → fct_sessions → marts for {staged}")

        dq = warehouse.run_quality_checks(con)
        failed = dq[dq.status == "fail"]
        log(f"[dq] {len(dq)} checks, {len(failed)} failed, {(dq.status == 'warn').sum()} warnings")
        if export:
            paths = warehouse.export_marts(con)
            log(f"[export] wrote {len(paths)} mart files to data/marts/")
    finally:
        con.close()
    log(f"done in {time.time() - t0:.1f}s → {db_path}")
    return {"counts": counts, "failed_checks": len(failed)}


def ensure_warehouse(db_path: Path = WAREHOUSE_PATH, log=print) -> None:
    """Build the warehouse on first run (used by the Streamlit app and Streamlit Cloud)."""
    if db_path.exists():
        con = warehouse.connect(db_path, read_only=True)
        try:
            if warehouse.table_exists(con, "mart_funnel"):
                return
        finally:
            con.close()
    run(db_path=db_path, log=log)


def main(argv=None) -> int:
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--demo-sessions", type=int, default=90_000,
                   help="number of simulated sessions (0 turns the demo dataset off)")
    p.add_argument("--skip-download", action="store_true", help="reuse the cached UCI file")
    p.add_argument("--no-export", action="store_true", help="skip the Parquet/CSV mart export")
    args = p.parse_args(argv)
    result = run(args.demo_sessions, args.skip_download, not args.no_export)
    return 1 if result["failed_checks"] else 0


if __name__ == "__main__":
    sys.exit(main())
