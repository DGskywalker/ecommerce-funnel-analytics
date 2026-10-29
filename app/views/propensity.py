import plotly.graph_objects as go
import streamlit as st

import charts
import common as c

ctx = c.ctx()
spec = ctx.spec

st.title("Purchase propensity")
st.caption("Which session traits predict a purchase? Trained on the whole dataset; sidebar filters don't apply here.")
c.dataset_banner(ctx)

proxy_label = "Include PageValues" if ctx.dataset == "uci" else "Include in-session engagement (page views, time)"
proxy_help = ("PageValues is computed from pages that come before a transaction, so it partly "
              "encodes the outcome." if ctx.dataset == "uci" else
              "Checkout pages inflate page views and time on site. Turn this off to keep only what "
              "is known when the session starts, which is what targeting needs.")
include = st.toggle(proxy_label, value=False, help=proxy_help, key=f"proxy_{ctx.dataset}")

res = c.train_model(ctx.dataset, include)
best = res.metrics[res.metrics["best"]].iloc[0]

k = st.columns(4)
k[0].metric("ROC AUC (best model)", f"{best['roc_auc']:.3f}")
k[1].metric("PR AUC", f"{best['pr_auc']:.3f}", f"base rate {res.base_rate:.1%}", delta_color="off")
k[2].metric("Top-decile lift", f"{best['top_decile_lift']:.1f}×")
k[3].metric("Purchases caught in top 10%", c.pct(best["top_decile_capture"]))

st.dataframe(
    res.metrics.rename(columns={"model": "Model", "roc_auc": "ROC AUC", "pr_auc": "PR AUC",
                                "brier": "Brier", "top_decile_lift": "Top-decile lift",
                                "top_decile_capture": "Top-decile capture", "best": "Selected"})
    .style.format({"ROC AUC": "{:.3f}", "PR AUC": "{:.3f}", "Brier": "{:.4f}",
                   "Top-decile lift": "{:.2f}×", "Top-decile capture": "{:.1%}"}),
    hide_index=True, use_container_width=True,
)
st.caption(f"Stratified hold-out: {res.n_train:,} training sessions, {res.n_test:,} test sessions. "
           "The model with the higher PR AUC is selected.")

a, b = st.columns(2)
with a:
    d = res.deciles
    fig = go.Figure(go.Bar(x=d["decile"].astype(str), y=d["lift"], marker=dict(color=c.SERIES[0], cornerradius=4),
                           customdata=d[["conversion_rate", "sessions"]].values,
                           hovertemplate="Decile %{x}<br>Lift %{y:.2f}×<br>CR %{customdata[0]:.2%}"
                                         "<br>Sessions %{customdata[1]:,.0f}<extra></extra>"))
    fig.add_hline(y=1, line=dict(color=c.INK_2, dash="dot", width=1))
    fig.update_layout(title="Lift by score decile (1 = highest scores)", xaxis=dict(title="Decile", type="category"),
                      yaxis=dict(title="Lift vs base rate", tickformat=".1f"))
    c.show(fig, height=340)
with b:
    d = res.deciles
    x = [0] + (d["decile"].astype(int) * 10).tolist()
    y = [0] + d["cum_capture"].tolist()
    fig = go.Figure()
    fig.add_trace(go.Scatter(x=[0, 100], y=[0, 1], mode="lines", name="Random",
                             line=dict(color=c.MUTED, dash="dot", width=1.5), hoverinfo="skip"))
    fig.add_trace(go.Scatter(x=x, y=y, mode="lines+markers", name="Model", line=dict(color=c.SERIES[0], width=2),
                             marker=dict(size=8, line=dict(color="white", width=2)),
                             hovertemplate="Top %{x}% of sessions → %{y:.0%} of purchases<extra></extra>"))
    fig.update_layout(title="Cumulative gains", xaxis=dict(title="% of sessions targeted", ticksuffix="%"),
                      yaxis=dict(title="% of purchases captured", tickformat=".0%"))
    c.show(fig, height=340)

imp = res.importance.head(12)
c.show(charts.bars(imp, "feature", "importance",
                   "Permutation importance (drop in PR AUC when the feature is shuffled)", fmt=".3f"))
st.caption("Permutation importance is computed on held-out sessions. It shows what the model relies on, "
           "not cause and effect.")
