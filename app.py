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
import statistics
from collections import Counter
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

# One distinct marker + colour per model on the range chart, keyed by model
# key (not position) so a model keeps its marker even when others are N/A.
MODEL_MARKERS = {
    "ddm_gordon": ("*", "gold"),
    "ddm_two_stage": ("s", "tab:blue"),
    "fcfe": ("^", "tab:red"),
    "pe_comps": ("o", "tab:green"),
    "pb_comps": ("D", "purple"),
    "ev_ebita": ("p", "orange"),
    "book_value": ("h", "cyan"),
    "liquidation": ("X", "magenta"),
    "replacement_cost": ("v", "brown"),
}


@st.cache_data
def load_snapshot():
    with open(SNAP) as f:
        return json.load(f)


@st.cache_data
def load_history():
    p = ROOT / "data" / "snapshot" / "history.json"
    if not p.exists():
        return None
    try:
        with open(p) as f:
            return json.load(f)
    except Exception:
        return None



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
    st.set_page_config(page_title="S&P 500 - Equity Valuation: 9 Models", layout="wide")
    # Sidebar nav is hidden: the app is a single-page lookup, and the
    # changelog page is reached via the link under the title (USMS pattern).
    st.markdown("<style>[data-testid='stSidebarNav']{display:none;}</style>",
                unsafe_allow_html=True)
    data = load_snapshot()
    hist = load_history()
    man, tickers = data["manifest"], data["tickers"]

    st.title("S&P 500 - Equity Valuation: 9 Models")
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
    tab_lookup, tab_breadth = st.tabs(["Ticker lookup", "Market breadth"])


    with tab_lookup:
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

        vals = [(label, key, r["models"][key]) for label, _, key in MODEL_ROWS
                if r["models"].get(key) is not None]
        if vals and price:
            fig, ax = plt.subplots(figsize=(9, 3.5))
            for label, key, x in vals:
                marker, color = MODEL_MARKERS[key]
                ax.scatter([x], [label], marker=marker, color=color, s=100,
                           edgecolors="black", linewidths=0.5, zorder=3)
            ax.axvline(price, color="red", linestyle="--", label=f"Price ${price:,.2f}")
            # Summary lines over the plotted model values, each its own colour
            # (and linestyle, so they stay distinct from each other and the
            # price line). Mode = most common whole-dollar-rounded value; with
            # continuous values a repeat is what makes a mode meaningful, so no
            # mode line is drawn when every rounded value is unique.
            xs_all = [x for _, _, x in vals]
            mean_v = statistics.mean(xs_all)
            median_v = statistics.median(xs_all)
            rounded = Counter(round(x) for x in xs_all)
            mode_v = None
            if max(rounded.values()) > 1:
                mode_v = min(v for v, c in rounded.items()
                             if c == max(rounded.values()))
            ax.axvline(mean_v, color="black", linestyle="-", linewidth=1.5,
                       label=f"Mean ${mean_v:,.2f}")
            ax.axvline(median_v, color="navy", linestyle="-.", linewidth=1.5,
                       label=f"Median ${median_v:,.2f}")
            if mode_v is not None:
                ax.axvline(mode_v, color="olive", linestyle=":", linewidth=1.8,
                           label=f"Mode ${mode_v:,.0f}")
            ax.set_xlabel("US$/share")
            ax.legend()
            ax.grid(axis="x", alpha=0.3)
            st.pyplot(fig)
            if mode_v is None:
                st.caption("Mode: none — no two models round to the same whole dollar.")

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

        if hist is not None and sym in hist["tickers"]:
            st.subheader("Valuation history")
            hd = hist["tickers"][sym]
            hdates = [d for d in hist["dates"] if d in hd]
            hrows = [{"Date": d,
                      "Price": f"${hd[d]['price']:,.2f}" if hd[d]["price"] else "N/A",
                      "Mean model": f"${hd[d]['mean']:,.2f}" if hd[d]["mean"] else "N/A",
                      "Median model": f"${hd[d]['median']:,.2f}" if hd[d]["median"] else "N/A",
                      "Models": hd[d]["n"]} for d in hdates]
            if len(hdates) >= 2:
                fig2, ax2 = plt.subplots(figsize=(9, 3.2))
                xs = list(range(len(hdates)))
                pr = [hd[d]["price"] for d in hdates]
                mn = [hd[d]["mean"] for d in hdates]
                md = [hd[d]["median"] for d in hdates]
                if all(v is not None for v in pr):
                    ax2.plot(xs, pr, color="red", linestyle="--", marker="o",
                             label="Price")
                if all(v is not None for v in mn):
                    ax2.plot(xs, mn, color="black", marker="o",
                             label="Mean model value")
                if all(v is not None for v in md):
                    ax2.plot(xs, md, color="navy", linestyle="-.", marker="o",
                             label="Median model value")
                ax2.set_xticks(xs)
                ax2.set_xticklabels(hdates)
                ax2.set_ylabel("US$/share")
                ax2.legend()
                ax2.grid(axis="y", alpha=0.3)
                st.pyplot(fig2)
            st.dataframe(hrows, use_container_width=True, hide_index=True)
            st.caption("History starts 2026-10-25 and grows with each daily "
                       "batch; it tracks the snapshot's own model values, not "
                       "revised fundamentals.")


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


    with tab_breadth:
        st.header("Market breadth — all constituents")
        st.write(
            "Breadth gauge from the latest snapshot: each constituent's mean "
            "model value versus its price. Read the distribution and its "
            "movement, not the level — present-value models sit structurally "
            "below market prices, so a negative mean upside is the norm, "
            "not a sell signal.")
        brows = []
        for s, r in tickers.items():
            vals = [v for v in r["models"].values() if v is not None]
            if not vals or not r["price"]:
                continue
            mean_v = statistics.mean(vals)
            brows.append({
                "symbol": s, "name": r["name"], "sector": r["sector"],
                "price": r["price"], "mean_model": mean_v,
                "upside": mean_v / r["price"] - 1, "n_models": len(vals),
                "all_above": all(v > r["price"] for v in vals),
                "all_below": all(v < r["price"] for v in vals),
                "range_pct": (max(vals) - min(vals)) / r["price"]})
        n_cov = len(brows)
        n_above = sum(1 for b in brows if b["upside"] > 0)
        ups = sorted(b["upside"] for b in brows)
        med_up = statistics.median(ups) if ups else None
        c1, c2, c3 = st.columns(3)
        c1.metric("Constituents covered", f"{n_cov}")
        c2.metric("Mean model above price",
                  f"{n_above} ({100.0 * n_above / n_cov:.1f}%)" if n_cov else "N/A")
        c3.metric("Median upside",
                  f"{med_up:+.1%}" if med_up is not None else "N/A")
        fig3, ax3 = plt.subplots(figsize=(9, 3.5))
        clipped = [max(-100.0, min(100.0, b["upside"] * 100)) for b in brows]
        n_lo = sum(1 for b in brows if b["upside"] * 100 < -100)
        n_hi = sum(1 for b in brows if b["upside"] * 100 > 100)
        ax3.hist(clipped, bins=30)
        ax3.axvline(0, color="red", linestyle="--", label="Price = mean model")
        ax3.set_xlabel("Mean model value vs price (%)")
        ax3.set_ylabel("Constituents")
        ax3.legend()
        ax3.grid(axis="y", alpha=0.3)
        st.pyplot(fig3)
        st.caption(f"Histogram window −100% to +100%; {n_lo} names below and "
                   f"{n_hi} above the window are bucketed at the edges "
                   "(extreme means come from single-model blowouts in the "
                   "snapshot, e.g. BRK.B per-share fundamentals).")
        st.subheader("Sector breadth")
        sec_rows = []
        for sec in sorted({b["sector"] for b in brows}):
            ss = [b for b in brows if b["sector"] == sec]
            su = sorted(b["upside"] for b in ss)
            sec_rows.append({
                "Sector": sec, "Names": len(ss),
                "Median upside": f"{statistics.median(su):+.1%}",
                "% above price": f"{100.0 * sum(1 for b in ss if b['upside'] > 0) / len(ss):.0f}%",
            })
        st.dataframe(sec_rows, use_container_width=True, hide_index=True)
        st.subheader("Consensus — every model on the same side of the price")
        above = [b for b in brows if b["all_above"]]
        below = [b for b in brows if b["all_below"]]
        st.write(f"All models above price: **{len(above)}** names; "
                 f"all models below price: **{len(below)}** names; "
                 f"the rest ({n_cov - len(above) - len(below)}) are split.")
        def cons_table(rows, key):
            rows = sorted(rows, key=key)[:25]
            return [{"Symbol": b["symbol"], "Name": b["name"],
                     "Sector": b["sector"],
                     "Price": f"${b['price']:,.2f}",
                     "Mean model": f"${b['mean_model']:,.2f}",
                     "Upside": f"{b['upside']:+.1%}",
                     "Models": b["n_models"]} for b in rows]
        if above:
            st.write("All models above price (highest upside first)")
            st.dataframe(cons_table(above, lambda b: -b["upside"]),
                         use_container_width=True, hide_index=True)
        if below:
            st.write("All models below price (deepest downside first)")
            st.dataframe(cons_table(below, lambda b: b["upside"]),
                         use_container_width=True, hide_index=True)
        st.subheader("Tightest agreement — models closest together")
        tight = sorted(brows, key=lambda b: b["range_pct"])[:10]
        st.dataframe([{"Symbol": b["symbol"], "Name": b["name"],
                       "Price": f"${b['price']:,.2f}",
                       "Model range": f"{b['range_pct']:.1%} of price",
                       "Mean upside": f"{b['upside']:+.1%}"} for b in tight],
                     use_container_width=True, hide_index=True)


if __name__ == "__main__":
    main()
