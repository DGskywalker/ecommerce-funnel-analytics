"""Entry point: `streamlit run app/streamlit_app.py`."""
import streamlit as st

st.set_page_config(page_title="Funnel Analytics", page_icon="📉", layout="wide")

import common  # noqa: E402  (sets sys.path and the plotly theme)

st.session_state["_ctx"] = common.sidebar()

pages = {
    "Analysis": [
        st.Page("views/overview.py", title="Executive overview", icon=":material/dashboard:", default=True),
        st.Page("views/funnel.py", title="Funnel & drop-off", icon=":material/filter_alt:"),
        st.Page("views/segments.py", title="Channels & devices", icon=":material/devices:"),
        st.Page("views/revenue.py", title="Revenue & opportunity", icon=":material/payments:"),
        st.Page("views/trends.py", title="Trends", icon=":material/show_chart:"),
        st.Page("views/propensity.py", title="Purchase propensity", icon=":material/model_training:"),
    ],
    "Reporting": [
        st.Page("views/writeup.py", title="Write-up & recommendations", icon=":material/article:"),
        st.Page("views/quality.py", title="Data quality & lineage", icon=":material/verified:"),
    ],
}
st.navigation(pages).run()
