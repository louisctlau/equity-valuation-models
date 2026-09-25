"""Run all valuations; write comparison.csv, findings.md, and range chart.

Usage: python scripts/run_all.py
"""
import csv
import json
import statistics
import sys
from pathlib import Path

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt

sys.path.insert(0, str(Path(__file__).resolve().parent))
from models import value_ticker, load_global

ROOT = Path(__file__).resolve().parent.parent
TICKERS = ["NVDA", "AMD", "MU", "AAPL", "META", "GOOG"]

MODEL_LABELS = [
    ("ddm_gordon", "1a. Gordon DDM"),
    ("ddm_two_stage", "1b. Two-stage DDM"),
    ("fcfe", "1c. FCFE model"),
    ("pe_comps", "2a. P/E comps"),
    ("pb_comps", "2b. P/B comps"),
    ("ev_ebita", "2c. EV/EBITA"),
    ("book_value", "3a. Book value"),
    ("liquidation", "3b. Liquidation"),
    ("replacement_cost", "3c. Replacement cost"),
]
CATS = {"1": "Present value", "2": "Multiples / relative", "3": "Asset-based"}


def main():
    g = load_global()
    mkt = json.loads((ROOT / "data" / "raw" / "market.json").read_text())
    results = {t: value_ticker(t) for t in TICKERS}

    # ---- comparison.csv
    docs = ROOT / "docs"
    with open(docs / "comparison.csv", "w", newline="") as f:
        w = csv.writer(f)
        w.writerow(["model", "category"] + TICKERS)
        for key, label in MODEL_LABELS:
            cat = CATS[label[0]]
            w.writerow([label, cat] + [
                ("" if results[t]["models"].get(key) is None
                 else round(results[t]["models"][key], 2)) for t in TICKERS])
        w.writerow(["Market price", "-"] + [round(results[t]["price"], 2)
                                            for t in TICKERS])

    # ---- range chart: min/median/max of applicable models vs market (log x)
    fig, axes = plt.subplots(2, 3, figsize=(15, 8), sharex=False)
    for ax, t in zip(axes.flat, TICKERS):
        r = results[t]
        vals = [v for v in r["models"].values() if v is not None and v > 0]
        lo, med, hi = min(vals), statistics.median(vals), max(vals)
        ax.hlines(0, lo, hi, colors="steelblue", linewidth=8, alpha=0.7)
        ax.plot(med, 0, "o", color="darkblue", ms=10, label=f"Model median ${med:,.0f}")
        ax.plot(r["price"], 0, "D", color="crimson", ms=10,
                label=f"Market ${r['price']:,.0f}")
        ax.set_xscale("log")
        ax.xaxis.set_major_formatter(plt.ScalarFormatter())
        ax.xaxis.set_minor_formatter(plt.NullFormatter())
        ax.tick_params(axis="x", which="minor", labelbottom=False)
        ax.set_yticks([])
        ax.set_title(t, fontweight="bold")
        ax.legend(fontsize=8, loc="upper left")
        ax.grid(True, axis="x", alpha=0.3)
    fig.suptitle("Equity valuation triangulation — 9 models per ticker vs market price\n"
                 "(blue bar = model range, dot = median, red diamond = market; log scale)",
                 fontsize=12, fontweight="bold")
    fig.tight_layout()
    (docs / "charts").mkdir(parents=True, exist_ok=True)
    fig.savefig(docs / "charts" / "valuation_ranges.png", dpi=110)
    plt.close(fig)

    # ---- findings.md
    rf, erp = results["NVDA"]["rf"], g["erp"]
    L = []
    L.append("# Equity Valuation — 9 Models × 6 Mega-Caps\n")
    L.append(f"Valuation date: **{results['NVDA']['valuation_date']}** · "
             f"Risk-free rate **{rf:.2%}** (US 10Y ^TNX) · ERP **{erp:.1%}** · "
             "Cost of equity via CAPM (β from Yahoo Finance).\n")
    L.append("Three valuation families, three models each. All assumptions are "
             "editable in `assumptions/`; re-run with `python scripts/run_all.py`.\n")
    L.append("## 1. Present value models (discounted at cost of equity)\n")
    L.append("- **1a. Constant-growth (Gordon) DDM:** V₀ = D₁/(kₑ−g). "
             "g capped at 5% — raw ROE × retention (e.g. AAPL 149%, NVDA 117%) "
             "is not sustainable forever.")
    L.append("- **1b. Two-stage DDM:** dividends grow at g₁ for 5 years "
             "(per-ticker assumption), then Gordon at 3% stable growth.")
    L.append("- **1c. FCFE model:** FCFE₀ = NI + D&A − capex − ΔWC + net borrowing "
             "(latest annual cash-flow statement); 5-year projection at per-ticker "
             "growth, Gordon terminal at 2.75%.\n")
    L.append("**Limitation stated upfront:** DDM values are tiny for low-payout "
             "growers (NVDA $0.52/yr, MU $0.53/yr) — the math is honest, the "
             "dividend policy is the constraint. AMD pays no dividend: both DDM "
             "models are N/A and FCFE carries the present-value leg.\n")
    L.append("## 2. Multiplier / relative value models\n")
    L.append("- **2a. P/E comps:** median peer trailing P/E × company TTM EPS. "
             "Peer sets in `assumptions/peers.json` (semis, large-cap tech, "
             "ad platforms).")
    L.append("- **2b. P/B comps:** median peer P/B × book value per share "
             "(statement equity / diluted shares).")
    L.append("- **2c. EV/EBITA:** median peer EV/EBIT × company EBIT "
             "(**assumption:** EBITA ≈ EBIT — amortization not disclosed "
             "separately), then equity = EV − debt + cash, per share.\n")
    L.append("**Stated caveats:** MU's TTM EPS ($44.19) is a cyclical peak — "
             "peer P/E × peak earnings overstates. AMD's book value is inflated "
             "by acquisition goodwill (Xilinx) — P/B comps overstate.\n")
    L.append("## 3. Asset-based models\n")
    L.append("- **3a. Book value:** statement equity / diluted shares.")
    L.append("- **3b. Liquidation:** cash 100%, receivables 85%, inventory 55%, "
             "other current 75%, PPE 50%, other non-current 40%, goodwill and "
             "intangibles 0% — less all liabilities, per share. "
             "**Assumption:** distressed-sale discounts are judgmental; "
             "AAPL's result is negative because buybacks have thinned equity "
             "below a haircut asset base — a real signal about downside "
             "protection, not a bug.")
    L.append("- **3c. Replacement cost:** current assets @1.0×, PPE @1.35×, "
             "other tangible non-current @1.15×, less liabilities. "
             "**Assumption:** construction-cost inflation premium is an estimate.\n")
    L.append("## Per-ticker results (US$/share)\n")
    for t in TICKERS:
        r = results[t]
        L.append(f"### {t} — market ${r['price']:,.2f} · kₑ {r['ke']:.2%} "
                 f"(β {r['beta']:.2f}) · dividend ${r['dividend_ann']:.2f}/yr\n")
        L.append("| Model | Value | vs market |")
        L.append("|---|---|---|")
        for key, label in MODEL_LABELS:
            v = r["models"].get(key)
            if v is None:
                L.append(f"| {label} | N/A | — |")
            else:
                u = v / r["price"] - 1
                L.append(f"| {label} | ${v:,.2f} | {u:+.1%} |")
        vals = [v for v in r["models"].values() if v is not None and v > 0]
        med = statistics.median(vals)
        L.append(f"\nModel median: **${med:,.2f}** ({med/r['price']-1:+.1%} vs market) "
                 f"· range ${min(vals):,.2f}–${max(vals):,.2f}.\n")
        for n in r["notes"]:
            L.append(f"> {n}\n")
    L.append("## Cross-model read\n")
    L.append("- **Present-value models** (FCFE-led) sit well below market for "
             "all six — at a 5.18% risk-free rate and CAPM discount rates of "
             "10–16%, the market is pricing growth/risk the models don't grant.")
    L.append("- **Multiples** mostly point the other way (P/E comps above market "
             "for NVDA, META, GOOG) — the market values these names like their "
             "peers, which are themselves richly priced.")
    L.append("- **Asset-based** values anchor the downside: $3–$104/share. "
             "Liquidation is the floor; for AAPL it is negative — equity "
             "holders rely entirely on franchise value.")
    L.append("- The honest conclusion is the **range**, not a point: e.g. NVDA "
             "$3–$334 across models (median ~$61 ex-distortions), AAPL −$9–$251. "
             "No single model is 'right'; the families disagree because they "
             "measure different things (cash distributions vs peer pricing vs "
             "asset claims).\n")
    L.append("## Re-run\n")
    L.append("```bash\npython3 -m venv .venv && .venv/bin/pip install "
             "yfinance pandas numpy matplotlib\n"
             ".venv/bin/python scripts/fetch_data.py  # refresh market data\n"
             ".venv/bin/python scripts/run_all.py      # rebuild docs/\n```\n")
    L.append("Data: Yahoo Finance via `yfinance` (statements, prices, dividends, "
             "peer multiples). No API key.")
    (docs / "findings.md").write_text("\n".join(L))
    print("wrote comparison.csv, findings.md, charts/valuation_ranges.png")


if __name__ == "__main__":
    main()
