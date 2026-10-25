"""Changelog — version history for the S&P 500 Valuation app."""
from pathlib import Path

import streamlit as st

st.set_page_config(page_title="Changelog — S&P 500 - Equity Valuation: 9 Models", layout="wide")
# Sidebar nav stays hidden; navigation is the link under the title in app.py.
st.markdown("<style>[data-testid='stSidebarNav']{display:none;}</style>",
            unsafe_allow_html=True)

st.title("Changelog")
st.caption("Every shipped change to the S&P 500 Valuation app, newest first.")
st.page_link("app.py", label="← Back to dashboard")
st.divider()

md = (Path(__file__).resolve().parent.parent / "CHANGELOG.md").read_text()
st.markdown(md)
