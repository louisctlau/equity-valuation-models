"""S&P 500 Valuation app — ticker lookup over the daily snapshot.

Reads data/snapshot/latest.json (built by scripts/sp500_build_snapshot.py).
No live market calls at request time: the snapshot is the data.

9 models, 3 families (same engine as the 6-ticker study):
  1a Gordon DDM, 1b two-stage DDM, 1c FCFE model,
  2a P/E comps, 2b P/B comps, 2c EV/EBITA (sector medians, not hand peers),
  3a book value, 3b liquidation, 3c replacement cost.
Sensitivity grids are computed live from the snapshot's stored inputs.
"""
import json
from datetime import datetime
from pathlib import Path
from zoneinfo import ZoneInfo

import matplotlib.pyplot as plt
import streamlit as st

ROOT = Path(__file__).resolve().parent
SNAP = ROOT / "data" / "snapshot" / "latest.json"

MODEL_ROWS = [
    ("1a. Gordon DDM", "Present value", "ddm_gordon"),
    ("1b. Two-stage DDM", "Present value", "ddm_two_stage"),
    ("1c. FCFE model", "Present value", "fcfe"),
    ("2a. P/E comps", "Multiples / relative", "pe_comps"),
    ("2b. P/B comps", "Multiples / relative", "pb_comps"),
    ("2c. EV/EBITA", "Multiples / relative", "ev_ebita"),
    ("3a. Book value", "Asset-based", "book_value"),
    ("3b. Liquidation", "Asset-based", "liquidation"),
    ("3c. Replacement cost", "Asset-based", "replacement_cost"),
]


@st.cache_data
def load_snapshot():
    with open(SNAP) as f:
        return json.load(f)


def gordon_grid(d0, ke, g0):
    """V0 = D0*(1+g)/(ke-g) over ke ±2pp x g in {1..5%}."""
    kes = [ke + d for d in (-0.02, -0.01, -0.005, 0.0, 0.005, 0.01, 0.02)]
    gs = [0.01, 0.02, 0.03, 0.04, 0.05]
    rows = {}
    for k in kes:
        row = {}
        for g in gs:
            row[f"g={g:.0%}"] = round(d0 * (1 + g) / (k - g), 2) if k > g else None
        rows[f"ke={k:.2%}"] = row
    return rows


def fcfe_grid(f0, sh, ke, g_term0, g5):
    """Project 5y at g5, Gordon terminal over ke x terminal-g grid."""
    kes = [ke + d for d in (-0.02, -0.01, -0.005, 0.0, 0.005, 0.01, 0.02)]
    gts = [0.015, 0.02, 0.0275, 0.035, 0.04]
    rows = {}
    for k in kes:
        row = {}
        for gt in gts:
            if k <= gt or not sh:
                row[f"gt={gt:.2%}"] = None
                continue
            pv, f = 0.0, f0
            for t in range(1, 6):
                f *= (1 + g5)
                pv += f / (1 + k) ** t
            pv += f * (1 + gt) / (k - gt) / (1 + k) ** 5
            row[f"gt={gt:.2%}"] = round(pv / sh, 2)
        rows[f"ke={k:.2%}"] = row
    return rows


def batch_label(man):
    """Display stamp for the last batch: '2026-10-25 03:24 EDT' when the
    manifest recorded a timestamp, else the snapshot date."""
    raw = man.get("snapshot_datetime")
    if raw:
        try:
            dt = datetime.fromisoformat(raw).astimezone(ZoneInfo("America/Toronto"))
            return dt.strftime("%Y-%m-%d %H:%M %Z")
        except Exception:
            return raw
    return man["snapshot_date"]


def main():
    st.set_page_config(page_title="S&P 500 Valuation — 9 Models", layout="wide")
    # Sidebar nav is hidden: the app is a single-page lookup, and the
    # changelog page is reached via the link under the title (USMS pattern).
    st.markdown("<style>[data-testid='stSidebarNav']{display:none;}</style>",
                unsafe_allow_html=True)
    data = load_snapshot()
    man, tickers = data["manifest"], data["tickers"]

    st.title("S&P 500 Valuation — 9 Models")
    st.markdown("<p style='color:red;'>For educational and experimental purposes "
                "only. Not investment advice.</p>",
                unsafe_allow_html=True)
    st.caption(
        f"Last batch loaded **{batch_label(man)}** · {man['ok']} of {man['universe']} "
        f"constituents valued · {len(man['failed'])} failed · "
        f"risk-free {man['rf']:.2%} (^TNX) · ERP {man['erp']:.1%} · "
        f"refreshed daily. Sector medians anchor the relative models."
    )
    st.page_link("pages/changelog.py", label="Changelog")

    options = sorted(tickers.keys())
    labels = {s: f"{s} — {tickers[s]['name']}" for s in options}
    default = options.index("NVDA") if "NVDA" in options else 0
    sym = st.selectbox("Company", options, index=default,
                       format_func=lambda s: labels[s])
    r = tickers[sym]
    price = r["price"]

    c1, c2, c3, c4 = st.columns(4)
    c1.metric("Market price", f"${price:,.2f}" if price else "N/A")
    c2.metric("Sector", r["sector"])
    c3.metric("Cost of equity", f"{r['ke']:.2%}")
    c4.metric("Statements FY end", r["fy_end"])
    st.write(
        f"{r['sub_industry']} · β {r['beta']:.2f} · annual dividend "
        f"${r['dividend_ann']:.2f} · shares {r['shares']/1e9:.2f}B · "
        f"FCFE base ${r['fcfe_base']/1e9:.1f}B"
    )

    st.subheader("Model values (US$/share)")
    rows = []
    for label, cat, key in MODEL_ROWS:
        v = r["models"].get(key)
        rows.append({
            "Model": label, "Category": cat,
            "Value": f"${v:,.2f}" if v is not None else "N/A",
            "vs price": (f"{(v/price-1):+.1%}" if (v is not None and price)
                         else "—"),
        })
    st.dataframe(rows, use_container_width=True, hide_index=True)

    vals = [(label, r["models"][key]) for label, _, key in MODEL_ROWS
            if r["models"].get(key) is not None]
    if vals and price:
        fig, ax = plt.subplots(figsize=(9, 3.5))
        names = [v[0] for v in vals]
        xs = [v[1] for v in vals]
        ax.scatter(xs, names, s=60, zorder=3)
        ax.axvline(price, color="red", linestyle="--", label=f"Price ${price:,.2f}")
        ax.set_xlabel("US$/share")
        ax.legend()
        ax.grid(axis="x", alpha=0.3)
        st.pyplot(fig)

    med = r.get("sector_medians", {})
    if med:
        st.subheader("Relative-model anchors (sector medians)")
        st.write(
            " · ".join(
                f"{k}: {v['value']:.2f} ({v['source']})"
                for k, v in med.items() if v["value"] is not None)
        )

    st.subheader("Sensitivity")
    a = r["assumptions"]
    if r["dividend_ann"] > 0:
        st.write("Gordon DDM — value vs cost of equity and dividend growth")
        st.dataframe(gordon_grid(r["dividend_ann"], r["ke"], a["gordon_g"]),
                     use_container_width=True)
    if r["fcfe_base"] is not None and r["shares"]:
        st.write("FCFE model — value vs cost of equity and terminal growth "
                 f"(5y growth {a['fcfe_g']:.1%})")
        st.dataframe(fcfe_grid(r["fcfe_base"], r["shares"], r["ke"],
                               a["terminal_g"], a["fcfe_g"]),
                     use_container_width=True)

    if r["notes"] or r["fallbacks"]:
        st.subheader("Notes")
        for n in r["notes"]:
            st.write(f"- {n}")
        for fb in r["fallbacks"]:
            st.write(f"- Data fallback: {fb}")

    with st.expander("Methodology, assumptions and limitations"):
        st.write(
            "- Present-value models discount at CAPM cost of equity "
            "(live β, live ^TNX, ERP 4.5%). Gordon g is capped at 5%; "
            "two-stage DDM uses a 5-year dividend CAGR (clipped to 18%) "
            "then 3% stable; FCFE projects 5 years at a 5-year FCFE CAGR "
            "(clipped to 20%) then 2.75% terminal. Fallbacks: 5% dividend "
            "growth, 8% FCFE growth when history is unusable.\n"
            "- Relative models use the median trailing P/E, P/B and "
            "EV/EBIT of the company's own GICS sector, computed from this "
            "same snapshot (index-wide median if a sector has fewer than "
            "5 valid names). P/B is N/A when equity is ≤ 0; P/E is N/A "
            "when EPS ≤ 0; EV/EBITA is N/A when EBIT ≤ 0.\n"
            "- Asset-based models use the study's liquidation recovery "
            "schedule (cash 100%, receivables 85%, inventory 55%, PPE 50%, "
            "goodwill/intangibles 0%) and replacement multiples "
            "(PPE 1.35×, other tangible non-current 1.15×).\n"
            "- Financials break the model set: FCFE is ill-defined for "
            "banks and EV/EBIT is meaningless when interest is operating "
            "income — treat those outputs with scepticism.\n"
            "- Data: Yahoo Finance via yfinance (unofficial, no licence), "
            "statements as filed; each ticker's statement fiscal year-end "
            "is shown above. Values are a range across disagreeing "
            "families, not a point estimate or investment advice."
        )
    if man["failed"]:
        with st.expander(f"Failed tickers ({len(man['failed'])})"):
            st.write(", ".join(man["failed"]))


if __name__ == "__main__":
    main()
