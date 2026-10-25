#!/usr/bin/env python3
"""Prototype: fetch the original 6 tickers via yfinance and run the
published engine's Category 1 + 3 models on fresh data.

Category 2 (multiples) is NOT computed here: Louis dropped the peer
comparison, so its anchor becomes the S&P 500 sector median in the full
build. This prototype validates the company-side inputs for Category 2
(EPS, book value/share, EBIT, debt, cash, shares) and reports them.

Comparability choices (to isolate mapping error from data drift):
- Same per-ticker assumptions as assumptions/<TICKER>.json and same
  global params (stable_g, terminal_g, liquidation schedule, replacement
  params) as the Sep 25 run.
- Same rf (5.184%) and ERP (4.5%) as the Sep 25 run. Live ^TNX is
  fetched and reported as a memo only.
- Beta, dividends, shares, price and statements are fresh from yfinance.

Output: prototype_yf/outputs/prototype_comparison.csv + a JSON detail file.
"""
import csv
import json
import sys
import time
import warnings
from pathlib import Path

warnings.filterwarnings("ignore")
sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "scripts"))

import yfinance as yf  # noqa: E402

from models import (  # noqa: E402
    book_value, cost_of_equity, ddm_gordon, ddm_two_stage, fcfe_base,
    fcfe_model, liquidation, replacement_cost, shares_out,
)

ROOT = Path(__file__).resolve().parent.parent
OUT = Path(__file__).resolve().parent / "outputs"
OUT.mkdir(parents=True, exist_ok=True)

TICKERS = ["NVDA", "AMD", "MU", "AAPL", "META", "GOOG"]

# Generic match: strip spaces + casefold. Explicit aliases where the
# engine name has no exact yfinance counterpart.
ALIASES = {
    "Net Income": ["NetIncome", "NetIncomeFromContinuingOperationNetMinorityInterest",
                   "NetIncomeFromContinuingAndDiscontinuedOperation",
                   "NetIncomeCommonStockholders"],
    "Depreciation And Amortization": ["ReconciledDepreciation",
                                      "DepreciationAmortizationDepletion",
                                      "DepreciationAndAmortization"],
    "Change In Working Capital": ["ChangeInWorkingCapital"],
    "Issuance Of Debt": ["IssuanceOfDebt", "LongTermDebtIssuance",
                         "NetIssuanceOfDebt"],
    "Repayment Of Debt": ["RepaymentOfDebt", "LongTermDebtPayments"],
    "Receivables": ["Receivables", "NetAccountsReceivable"],
    "Other Intangible Assets": ["OtherIntangibleAssets"],
    "Goodwill And Other Intangible Assets": ["GoodwillAndOtherIntangibleAssets"],
}


def _norm(s):
    return "".join(str(s).split()).casefold()


def pick(row, *names):
    """row: dict keyed by yfinance labels. Return value for the first
    engine name that resolves, or None."""
    by_norm = {_norm(k): v for k, v in row.items() if v is not None}
    for n in names:
        for cand in ALIASES.get(n, [n]):
            v = by_norm.get(_norm(cand))
            if v is not None:
                try:
                    if v != v:  # NaN
                        continue
                except Exception:
                    pass
                return float(v)
    return None


def latest_col(df):
    if df is None or df.empty:
        return {}
    col = max(df.columns)
    s = df[col]
    return {str(k): v for k, v in s.items()}


def build_company(t):
    tk = yf.Ticker(t)
    inc = latest_col(tk.get_income_stmt())
    bs = latest_col(tk.get_balance_sheet())
    cf = latest_col(tk.get_cashflow())
    info = tk.get_info()
    divs = tk.dividends
    div_list = []
    if divs is not None and len(divs):
        div_list = [[str(d.date()), float(v)] for d, v in divs.tail(8).items()]
    hist = tk.history(period="5d")
    price = None
    if hist is not None and not hist.empty and "Close" in hist:
        price = float(hist["Close"].mean())
    if price is None:
        price = info.get("currentPrice")

    # Map yfinance rows onto the engine's expected names.
    inc_m = {n: pick(inc, n) for n in
             ["Net Income", "EBIT", "Operating Income"]}
    bs_m = {n: pick(bs, n) for n in
            ["Stockholders Equity", "Total Equity Gross Minority Interest",
             "Common Stock Equity", "Total Liabilities Net Minority Interest",
             "Total Assets", "Total Debt", "Cash And Cash Equivalents",
             "Cash Cash Equivalents And Short Term Investments",
             "Other Short Term Investments", "Accounts Receivable",
             "Receivables", "Net Accounts Receivable", "Inventory",
             "Other Current Assets", "Prepaid Assets", "Net PPE", "Goodwill",
             "Other Intangible Assets", "Goodwill And Other Intangible Assets",
             "Other Non Current Assets", "Investments And Advances",
             "Other Investments", "Current Assets", "Total Non Current Assets",
             "Ordinary Shares Number"]}
    cf_m = {n: pick(cf, n) for n in
            ["Depreciation And Amortization",
             "Depreciation Amortization Depletion", "Capital Expenditure",
             "Change In Working Capital", "Issuance Of Debt",
             "Long Term Debt Issued", "Net Issuance Of Debt",
             "Repayment Of Debt", "Long Term Debt Payments"]}

    # Fill the engine's _get fallbacks: keep only resolved names.
    inc_d = {k: v for k, v in inc_m.items() if v is not None}
    bs_d = {k: v for k, v in bs_m.items() if v is not None}
    cf_d = {k: v for k, v in cf_m.items() if v is not None}

    raw = {"dividends": div_list,
           "dilutedShares": bs_d.get("Ordinary Shares Number")
                            or info.get("sharesOutstanding")}
    c = {"raw": raw, "info": info,
         "inc": inc_d, "bs": bs_d, "cf": cf_d, "price": price}
    return c, {"inc_missing": [k for k, v in inc_m.items() if v is None],
               "bs_missing": [k for k, v in bs_m.items() if v is None],
               "cf_missing": [k for k, v in cf_m.items() if v is None]}


def main():
    g = json.loads((ROOT / "assumptions" / "global.json").read_text())
    orig = {}
    with open(ROOT / "docs" / "comparison.csv") as f:
        for row in csv.DictReader(f):
            orig[row["model"]] = row

    # Live ^TNX memo (not used in the diff run).
    try:
        tnx = yf.Ticker("^TNX").history(period="5d")
        tnx_last = None if tnx.empty else float(tnx["Close"].iloc[-1]) / 100
    except Exception as e:
        tnx_last = f"fetch failed: {type(e).__name__}"
    print("live ^TNX (memo):", tnx_last)

    rf, erp = 0.05184, g["erp"]
    results, details = {}, {}
    for t in TICKERS:
        a = json.loads((ROOT / "assumptions" / f"{t}.json").read_text())
        c, missing = build_company(t)
        ke, beta = cost_of_equity(c["info"], rf, erp)
        sh = shares_out(c)
        d0 = sum(v for _, v in c["raw"]["dividends"][-4:]) if c["raw"]["dividends"] else 0.0
        models = {}
        if d0 > 0:
            models["ddm_gordon"] = ddm_gordon(c, ke, a["gordon_g"])
            models["ddm_two_stage"] = ddm_two_stage(c, ke, a["div_g1"], g["stable_g"])
        else:
            models["ddm_gordon"] = None
            models["ddm_two_stage"] = None
        models["fcfe"] = fcfe_model(c, ke, a["fcfe_g"], g["terminal_g"], sh)
        models["book_value"] = book_value(c, sh)
        liq = liquidation(c, sh, g["liquidation_schedule"])
        models["liquidation"] = liq["per_share"] if liq else None
        models["replacement_cost"] = replacement_cost(c, sh, g["replacement_params"])
        results[t] = models
        details[t] = {
            "price": c["price"], "ke": ke, "beta": beta, "shares": sh,
            "dividend_ann": d0, "fcfe_base": fcfe_base(c),
            "missing_fields": missing,
            "cat2_inputs": {
                "trailingEps": c["info"].get("trailingEps"),
                "trailingPE": c["info"].get("trailingPE"),
                "priceToBook": c["info"].get("priceToBook"),
                "ebit": c["inc"].get("EBIT"),
                "equity": c["bs"].get("Stockholders Equity"),
                "totalDebt": c["bs"].get("Total Debt"),
                "cash": c["bs"].get("Cash And Cash Equivalents"),
                "enterpriseValue": c["info"].get("enterpriseValue"),
                "sector": c["info"].get("sector"),
                "industry": c["info"].get("industry"),
            },
        }
        print(f"{t}: price={c['price'] and round(c['price'], 2)} beta={beta} "
              f"div_ann={round(d0, 3)} fcfe_base={fcfe_base(c) and round(fcfe_base(c))}")
        time.sleep(1)

    rows = [
        ("1a. Gordon DDM", "ddm_gordon"),
        ("1b. Two-stage DDM", "ddm_two_stage"),
        ("1c. FCFE model", "fcfe"),
        ("3a. Book value", "book_value"),
        ("3b. Liquidation", "liquidation"),
        ("3c. Replacement cost", "replacement_cost"),
    ]
    with open(OUT / "prototype_comparison.csv", "w", newline="") as f:
        w = csv.writer(f)
        w.writerow(["model", "category"] + TICKERS)
        for label, key in rows:
            cat = "Present value" if label.startswith("1") else "Asset-based"
            w.writerow([label, cat] + [
                "" if results[t][key] is None else round(results[t][key], 2)
                for t in TICKERS])
        w.writerow(["Market price", "-"] + [
            "" if details[t]["price"] is None else round(details[t]["price"], 2)
            for t in TICKERS])
    with open(OUT / "prototype_detail.json", "w") as f:
        json.dump({"live_tnx_memo": tnx_last, "tickers": details}, f, indent=1, default=str)
    print("wrote", OUT / "prototype_comparison.csv")

    print("\n=== diff vs Sep 25 (prototype - original) ===")
    for label, key in rows:
        o = orig[label]
        line = [label]
        for t in TICKERS:
            ov = o[t]
            pv = results[t][key]
            if ov == "" or pv is None:
                line.append(f"{t}: orig={ov or 'N/A'} new={'N/A' if pv is None else round(pv, 2)}")
            else:
                line.append(f"{t}: {round(pv - float(ov), 2):+}")
        print(" | ".join(line))


if __name__ == "__main__":
    main()
