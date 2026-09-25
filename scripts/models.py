"""Equity valuation engine — 3 categories, 9 models.

Category 1 — Present value (discounted at cost of equity, CAPM):
  ddm_gordon     Constant-growth (Gordon) dividend discount model
  ddm_two_stage  Two-stage dividend discount model (5y high growth + stable)
  fcfe           Free-cash-flow-to-equity model (5y projection + Gordon terminal)

Category 2 — Multiplier / relative value (peer medians):
  pe_comps       Peer median trailing P/E x company TTM EPS
  pb_comps       Peer median P/B x company book value per share
  ev_ebita       Peer median EV/EBIT x company EBIT (-> EV -> equity -> /share)
                 EBITA ~= EBIT: amortization not broken out; stated assumption.

Category 3 — Asset-based:
  book_value     Total stockholders' equity / diluted shares
  liquidation    Asset recovery schedule (stated discounts) less all liabilities
  replacement    Current assets @1.0x + PPE @1.35x + other tangible NCA @1.15x
                 less liabilities (stated construction-cost inflation assumption)

Reads:  data/raw/<TICKER>.json, data/raw/peers/<TICKER>.json,
        data/raw/market.json, assumptions/global.json,
        assumptions/peers.json, assumptions/<TICKER>.json
"""
import json
import statistics
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent


def _get(row, *names):
    for n in names:
        v = row.get(n)
        if v is not None:
            return v
    return None


def load_company(ticker):
    d = json.loads((ROOT / "data" / "raw" / f"{ticker}.json").read_text())
    inc, bs, cf = d["financials"], d["balance_sheet"], d["cashflow"]
    yi = sorted(inc.keys())[-1]
    yb = sorted(bs.keys())[-1]
    yc = sorted(cf.keys())[-1]
    return {
        "raw": d, "info": d["info"],
        "year": yi,
        "price": d.get("lastClose5d") or d["info"].get("currentPrice"),
        "inc": inc[yi], "bs": bs[yb], "cf": cf[yc],
    }


def load_global():
    return json.loads((ROOT / "assumptions" / "global.json").read_text())


def load_ticker_assumptions(ticker):
    return json.loads((ROOT / "assumptions" / f"{ticker}.json").read_text())


def cost_of_equity(info, rf, erp):
    beta = info.get("beta") or 1.0
    return rf + beta * erp, beta


def shares_out(c):
    return (c["raw"].get("dilutedShares")
            or c["bs"].get("Ordinary Shares Number")
            or c["info"].get("sharesOutstanding"))


def annualized_dividend(c):
    divs = c["raw"].get("dividends") or []
    if not divs:
        return 0.0
    return sum(v for _, v in divs[-4:])


# ---------------------------------------------------------------- category 1

def ddm_gordon(c, ke, g):
    """V0 = D1 / (ke - g). Requires ke > g and D0 > 0."""
    d0 = annualized_dividend(c)
    if d0 <= 0 or ke <= g:
        return None
    return d0 * (1 + g) / (ke - g)


def ddm_two_stage(c, ke, g1, g2, years=5):
    """High dividend growth g1 for `years`, then Gordon at g2."""
    d0 = annualized_dividend(c)
    if d0 <= 0 or ke <= g2:
        return None
    pv = 0.0
    d = d0
    for t in range(1, years + 1):
        d *= (1 + g1)
        pv += d / (1 + ke) ** t
    tv = d * (1 + g2) / (ke - g2)
    pv += tv / (1 + ke) ** years
    return pv


def fcfe_base(c):
    """FCFE0 = NI + D&A + capex_row(neg) + wc_change_row + net borrowing."""
    ni = _get(c["inc"], "Net Income") or 0
    da = _get(c["cf"], "Depreciation And Amortization",
              "Depreciation Amortization Depletion") or 0
    capex = _get(c["cf"], "Capital Expenditure") or 0          # negative outflow
    dwc = _get(c["cf"], "Change In Working Capital") or 0      # cash impact
    issued = _get(c["cf"], "Issuance Of Debt", "Long Term Debt Issued",
                  "Net Issuance Of Debt") or 0
    repaid = _get(c["cf"], "Repayment Of Debt", "Long Term Debt Payments") or 0
    return ni + da + capex + dwc + issued + repaid


def fcfe_model(c, ke, g_5y, g_terminal, shares, years=5):
    """Project FCFE years 1-5 at g_5y, Gordon terminal at g_terminal."""
    f0 = fcfe_base(c)
    if ke <= g_terminal or shares is None or shares <= 0:
        return None
    pv, f = 0.0, f0
    for t in range(1, years + 1):
        f *= (1 + g_5y)
        pv += f / (1 + ke) ** t
    tv = f * (1 + g_terminal) / (ke - g_terminal)
    pv += tv / (1 + ke) ** years
    return pv / shares


# ---------------------------------------------------------------- category 2

def peer_median(ticker, key):
    d = json.loads((ROOT / "data" / "raw" / "peers" / f"{ticker}.json").read_text())
    vals = []
    for p, pd_ in d["data"].items():
        if key == "ev_ebit":
            ev = pd_["info"].get("enterpriseValue")
            ebit = pd_.get("ebit")
            if ev and ebit and ebit > 0:
                vals.append(ev / ebit)
        else:
            v = pd_["info"].get(key)
            if v is not None and v > 0:
                vals.append(v)
    return statistics.median(vals) if vals else None


def pe_comps(c, ticker):
    med = peer_median(ticker, "trailingPE")
    eps = c["info"].get("trailingEps")
    if med is None or eps is None or eps <= 0:
        return None
    return med * eps


def pb_comps(c, ticker, shares):
    med = peer_median(ticker, "priceToBook")
    equity = _get(c["bs"], "Stockholders Equity",
                  "Total Equity Gross Minority Interest",
                  "Common Stock Equity")
    if med is None or equity is None or not shares:
        return None
    return med * (equity / shares)


def ev_ebita(c, ticker, shares):
    """Peer median EV/EBIT x company EBIT -> EV -> equity/share.
    EBITA ~= EBIT (amortization not disclosed separately)."""
    med = peer_median(ticker, "ev_ebit")
    ebit = _get(c["inc"], "EBIT", "Operating Income")
    if med is None or ebit is None or ebit <= 0 or not shares:
        return None
    ev = med * ebit
    debt = _get(c["bs"], "Total Debt") or c["info"].get("totalDebt") or 0
    cash = (_get(c["bs"], "Cash And Cash Equivalents",
                 "Cash Cash Equivalents And Short Term Investments")
            or c["info"].get("totalCash") or 0)
    return (ev - debt + cash) / shares


# ---------------------------------------------------------------- category 3

def total_liabilities(c):
    tl = _get(c["bs"], "Total Liabilities Net Minority Interest", "Total Liab")
    if tl is not None:
        return tl
    ta = _get(c["bs"], "Total Assets")
    te = _get(c["bs"], "Total Equity Gross Minority Interest",
              "Stockholders Equity")
    if ta is not None and te is not None:
        return ta - te
    return None


def book_value(c, shares):
    equity = _get(c["bs"], "Stockholders Equity",
                  "Total Equity Gross Minority Interest",
                  "Common Stock Equity")
    if equity is None or not shares:
        return None
    return equity / shares


def liquidation(c, shares, schedule):
    """Sum(asset x recovery rate) - total liabilities, per share."""
    if not shares:
        return None
    bs = c["bs"]
    buckets = [
        (["Cash And Cash Equivalents",
          "Cash Cash Equivalents And Short Term Investments"], "cash"),
        (["Other Short Term Investments"], "st_investments"),
        (["Accounts Receivable", "Receivables",
          "Net Accounts Receivable"], "receivables"),
        (["Inventory"], "inventory"),
        (["Other Current Assets", "Prepaid Assets"], "other_ca"),
        (["Net PPE"], "ppe"),
        (["Goodwill"], "goodwill"),
        (["Other Intangible Assets"], "intangibles"),
        (["Other Non Current Assets", "Investments And Advances",
          "Other Investments"], "other_nca"),
    ]
    recoverable = 0.0
    detail = {}
    for names, key in buckets:
        v = _get(bs, *names) or 0
        rate = schedule.get(key, 0)
        recoverable += v * rate
        detail[key] = {"gross": v, "rate": rate}
    tl = total_liabilities(c)
    if tl is None:
        return None
    net = recoverable - tl
    return {"per_share": net / shares, "recoverable": recoverable,
            "liabilities": tl, "net": net, "detail": detail}


def replacement_cost(c, shares, params):
    """Tangible assets at replacement multiples less liabilities, per share."""
    if not shares:
        return None
    bs = c["bs"]
    ca = _get(bs, "Current Assets") or 0
    ppe = _get(bs, "Net PPE") or 0
    goodwill = _get(bs, "Goodwill") or 0
    intang = _get(bs, "Other Intangible Assets",
                  "Goodwill And Other Intangible Assets") or 0
    if intang == (_get(bs, "Goodwill And Other Intangible Assets") or 0):
        intang = 0  # avoid double count when only the combined row exists
    nca = _get(bs, "Total Non Current Assets") or 0
    other_tangible_nca = max(nca - ppe - goodwill - intang, 0)
    repl = (ca * params.get("current_assets_mult", 1.0)
            + ppe * params.get("ppe_mult", 1.35)
            + other_tangible_nca * params.get("other_nca_mult", 1.15))
    tl = total_liabilities(c)
    if tl is None:
        return None
    return (repl - tl) / shares


# ---------------------------------------------------------------- driver

def value_ticker(ticker):
    g = load_global()
    a = load_ticker_assumptions(ticker)
    mkt = json.loads((ROOT / "data" / "raw" / "market.json").read_text())
    rf = mkt["risk_free_10y"] if mkt.get("risk_free_10y") else g["risk_free_fallback"]
    erp = g["erp"]

    c = load_company(ticker)
    ke, beta = cost_of_equity(c["info"], rf, erp)
    sh = shares_out(c)
    d0 = annualized_dividend(c)

    out = {"ticker": ticker, "valuation_date": c["raw"]["valuation_date"],
           "price": c["price"], "ke": ke, "beta": beta, "rf": rf, "erp": erp,
           "shares": sh, "dividend_ann": d0, "models": {}, "notes": []}

    # ---- category 1: present value
    if d0 > 0:
        out["models"]["ddm_gordon"] = ddm_gordon(c, ke, a["gordon_g"])
        out["models"]["ddm_two_stage"] = ddm_two_stage(
            c, ke, a["div_g1"], g["stable_g"])
    else:
        out["notes"].append("DDM models not applicable: company pays no dividend.")
    out["models"]["fcfe"] = fcfe_model(c, ke, a["fcfe_g"], g["terminal_g"], sh)
    out["fcfe_base"] = fcfe_base(c)

    # ---- category 2: multiples
    out["models"]["pe_comps"] = pe_comps(c, ticker)
    out["models"]["pb_comps"] = pb_comps(c, ticker, sh)
    out["models"]["ev_ebita"] = ev_ebita(c, ticker, sh)
    out["peer_medians"] = {
        "pe": peer_median(ticker, "trailingPE"),
        "pb": peer_median(ticker, "priceToBook"),
        "ev_ebit": peer_median(ticker, "ev_ebit"),
    }

    # ---- category 3: asset-based
    out["models"]["book_value"] = book_value(c, sh)
    liq = liquidation(c, sh, g["liquidation_schedule"])
    out["models"]["liquidation"] = liq["per_share"] if liq else None
    out["liquidation_detail"] = liq
    out["models"]["replacement_cost"] = replacement_cost(
        c, sh, g["replacement_params"])

    return out
