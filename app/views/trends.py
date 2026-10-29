import plotly.graph_objects as go
import streamlit as st

import charts
import common as c
from funnel_analytics import metrics as m

ctx = c.ctx()
spec, df = ctx.spec, ctx.df

st.title("Trends")
c.dataset_banner(ctx)
if c.empty_guard(ctx):
    st.stop()

if spec.time_grain == "day":
    grain = st.segmented_control("Grain", ["day", "week"], default="day", key="grain") or "day"
else:
    grain = "month"
    st.caption("This dataset records only the month of each session.")

t = m.trend(df, spec, grain)
c.show(charts.line(t, "period", [("sessions", "Sessions", c.SERIES[0])], "Sessions"), height=280)
ys = [("conversion_rate", "Conversion rate", c.SERIES[0])]
if grain == "day":
    ys.append(("cr_rolling", "7-day rolling", c.SERIES[1]))
c.show(charts.line(t, "period", ys, "Conversion rate (shaded: 95% CI)", yfmt=".2%",
                   band=("ci_low", "ci_high"), markers_col="anomaly"), height=320)
n_anom = int(t["anomaly"].sum())
if n_anom:
    st.caption(f"{n_anom} period(s) sit more than 2 standard deviations from the mean conversion rate.")

st.divider()
dim = st.segmented_control("Compare conversion over time by", ["device", "visitor_type", "channel"],
                           default="device", format_func=lambda d: spec.dim_labels[d].split(" (")[0],
                           key="trend_dim") or "device"
keep = 3 if dim != "channel" else 5
d = c.fold_other(df, ctx.dataset, dim, keep=keep)
cmap = c.color_map(ctx.dataset, dim, max_series=keep)
fig = go.Figure()
for seg in [s for s in c.segment_order(ctx.dataset, dim)[:keep] if s in set(d[dim])]:
    ts = m.trend(d[d[dim] == seg], spec, "week" if grain == "day" else grain)
    fig.add_trace(go.Scatter(x=ts["period"], y=ts["conversion_rate"], name=seg, mode="lines+markers",
                             line=dict(color=cmap.get(seg), width=2), marker=dict(size=8, line=dict(color="white", width=2)),
                             hovertemplate=f"{seg} %{{y:.2%}}<extra></extra>"))
fig.update_layout(title=f"{'Weekly' if grain == 'day' else 'Monthly'} conversion rate by "
                        f"{spec.dim_labels[dim].split(' (')[0].lower()}",
                  yaxis=dict(tickformat=".1%"), hovermode="x unified")
c.show(fig, height=340)

wk = m.segment_table(df.assign(day_type=df["is_weekend"].map({True: "Weekend", False: "Weekday"})),
                     "day_type", spec, ctx.mode)
a, b = st.columns(2)
for col, (_, r) in zip((a, b), wk.iterrows()):
    col.metric(f"{r['day_type']} conversion", c.pct(r["conversion_rate"], 2),
               f"{r['lift_vs_rest']:+.1%} vs {'weekday' if r['day_type'] == 'Weekend' else 'weekend'}")
