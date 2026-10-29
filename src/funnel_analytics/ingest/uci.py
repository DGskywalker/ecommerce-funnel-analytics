"""Download and load the UCI Online Shoppers Purchasing Intention dataset (CC BY 4.0)."""
from __future__ import annotations

import io
import urllib.request
import zipfile
from pathlib import Path

import duckdb

from ..config import UCI_CSV, UCI_URL


def download(force: bool = False, dest: Path = UCI_CSV, timeout: int = 60) -> Path:
    """Fetch the zip from the UCI repository and pull out the CSV. No login or key needed."""
    if dest.exists() and not force:
        return dest
    dest.parent.mkdir(parents=True, exist_ok=True)
    req = urllib.request.Request(UCI_URL, headers={"User-Agent": "funnel-analytics/1.0"})
    with urllib.request.urlopen(req, timeout=timeout) as resp:
        payload = resp.read()
    with zipfile.ZipFile(io.BytesIO(payload)) as zf:
        member = next(n for n in zf.namelist() if n.endswith(".csv"))
        dest.write_bytes(zf.read(member))
    return dest


def load_raw(con: duckdb.DuckDBPyConnection, csv_path: Path = UCI_CSV) -> int:
    """Load the CSV into raw_uci with a stable session_id (file order)."""
    con.execute(
        """
        CREATE OR REPLACE TABLE raw_uci AS
        SELECT 'uci-' || lpad(CAST(row_number() OVER () AS VARCHAR), 5, '0') AS session_id, *
        FROM read_csv(?, header = true, auto_detect = true)
        """,
        [str(csv_path)],
    )
    return con.execute("SELECT COUNT(*) FROM raw_uci").fetchone()[0]
