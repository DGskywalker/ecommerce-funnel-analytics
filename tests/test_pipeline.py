"""End-to-end: simulated GA4-schema data → warehouse → checks → metrics, in a temp DB."""
import pandas as pd

from funnel_analytics import metrics as m
from funnel_analytics import warehouse
from funnel_analytics.config import DATASETS
from funnel_analytics.ingest import ga4, simulate


def test_demo_pipeline_builds_and_passes_checks(tmp_path):
    con = warehouse.connect(tmp_path / "t.duckdb")
    simulate.load_raw(con, n_sessions=5_000, seed=1)
    assert warehouse.build_models(con) == ["demo"]

    dq = warehouse.run_quality_checks(con)
    assert (dq["status"] != "fail").all(), dq[dq.status == "fail"]

    df = con.execute("SELECT * FROM mart_funnel").df()
    assert df["sessions"].sum() == 5_000
    assert set(df["channel"]) <= {"Organic Search", "Direct", "Referral", "Paid Search",
                                  "Organic Social", "Email", "Obfuscated"}
    k = m.kpis(df, DATASETS["demo"])
    assert 0 < k["conversion_rate"] < 0.1
    assert k["revenue"] > 0


def test_ga4_export_loader_reads_bigquery_csv_layout(tmp_path):
    """A CSV laid out like the BigQuery export loads through the real GA4 path."""
    export = tmp_path / "ga4"
    export.mkdir()
    sample = simulate.generate(500, seed=3)
    sample.iloc[:300].to_csv(export / "part1.csv", index=False)
    sample.iloc[250:].to_csv(export / "part2.csv", index=False)  # overlapping rows get deduplicated

    con = warehouse.connect(tmp_path / "t.duckdb")
    assert ga4.load_raw(con, export) == 500
    assert warehouse.build_models(con) == ["ga4"]
    n = con.execute("SELECT COUNT(*) FROM fct_sessions WHERE dataset = 'ga4'").fetchone()[0]
    assert n == 500


def test_channel_grouping_macro():
    import duckdb

    con = duckdb.connect()
    warehouse._run_sql_file(con, "00_macros.sql")
    cases = pd.DataFrame({
        "src": ["google", "(direct)", "youtube.com", "google", "<Other>", None],
        "med": ["organic", "(none)", "referral", "cpc", "<Other>", None],
        "want": ["Organic Search", "Direct", "Referral", "Paid Search", "Obfuscated", "Unassigned"],
    })
    con.register("cases", cases)
    got = con.execute("SELECT channel_group(src, med) FROM cases").fetchall()
    assert [g[0] for g in got] == cases["want"].tolist()
