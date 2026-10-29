import streamlit as st

import common as c

ctx = c.ctx()

st.title("Data quality & lineage")

st.subheader("Lineage")
st.graphviz_chart(
    """
digraph {
  rankdir=LR; bgcolor="transparent";
  node [shape=box, style="rounded,filled", fontname="Helvetica", fontsize=11, color="#c7c6c0", fillcolor="#fcfcfb"];
  edge [color="#8a8984"];
  subgraph cluster_src { label="Sources (free, no API keys)"; fontsize=11; color="#e6e5e0";
    bq  [label="BigQuery sandbox\\nga4_obfuscated_sample_ecommerce", fillcolor="#cde2fb"];
    uci [label="UCI repository\\nOnline Shoppers (#468)", fillcolor="#cde2fb"];
    sim [label="GA4-schema simulator\\n(demo only)", fillcolor="#f0efec"]; }
  bq  -> raw_ga4  [label=" 01_session_funnel.sql → CSV", fontsize=9];
  uci -> raw_uci  [label=" HTTP download", fontsize=9];
  sim -> raw_demo;
  raw_ga4 -> stg_ga4; raw_demo -> stg_demo; raw_uci -> stg_uci; raw_uci -> uci_features;
  stg_ga4 -> fct_sessions; stg_demo -> fct_sessions; stg_uci -> fct_sessions;
  fct_sessions -> mart_funnel; fct_sessions -> mart_dataset_summary;
  mart_funnel -> dashboard [label=" metrics.py", fontsize=9];
  fct_sessions -> model [label=" model.py", fontsize=9]; uci_features -> model;
  mart_funnel -> exports [label=" Parquet / CSV", fontsize=9];
  dashboard [label="Streamlit dashboard", fillcolor="#86b6ef"];
  model [label="Propensity models", fillcolor="#86b6ef"];
  exports [label="data/marts/*\\n(Power BI / Looker Studio)", fillcolor="#86b6ef"];
}
""",
    use_container_width=True,
)

st.subheader("Datasets in the warehouse")
summary = c.query("SELECT * FROM mart_dataset_summary ORDER BY dataset")
st.dataframe(summary, hide_index=True, use_container_width=True)

st.subheader("Automated checks")
dq = c.quality_checks()
icon = {"pass": "✅ pass", "fail": "❌ fail", "warn": "⚠️ warn", "info": "ℹ️ info"}
st.dataframe(
    dq.assign(status=dq["status"].map(icon))[["dataset", "check", "status", "failing_rows", "total_rows",
                                               "pct", "description"]]
    .style.format({"failing_rows": "{:,.0f}", "total_rows": "{:,.0f}", "pct": "{:.2%}"}),
    hide_index=True, use_container_width=True,
)
st.caption("Errors fail the pipeline (non-zero exit code). Warnings and info rows are known properties of the "
           "source data, shown here so readers can judge the numbers.")
