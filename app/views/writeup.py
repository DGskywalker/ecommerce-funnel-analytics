import streamlit as st

import common as c
from funnel_analytics import writeup
from funnel_analytics.config import DOCS_DIR

ctx = c.ctx()

st.title("Write-up & recommendations")
tab_final, tab_auto = st.tabs(["Analyst write-up", f"Auto-draft: {ctx.spec.short}"])

with tab_final:
    path = DOCS_DIR / "WRITEUP.md"
    if path.exists():
        st.markdown(path.read_text())
        st.download_button("Download WRITEUP.md", path.read_bytes(), "WRITEUP.md", "text/markdown")
    else:
        st.info("docs/WRITEUP.md not found.")

with tab_auto:
    st.caption("Generated live from the full dataset (sidebar filters don't apply) by "
               "`funnel_analytics.writeup`. Use it as a first draft and edit it.")
    with c.connect() as con:
        md = writeup.build(con, ctx.dataset)
    st.markdown(md)
    st.download_button("Download draft", md.encode(), f"writeup_{ctx.dataset}_auto.md", "text/markdown")
