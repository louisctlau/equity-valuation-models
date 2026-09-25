"""Fetch company + peer financial data via yfinance.

Saves:
  data/raw/<TICKER>.json          company statements, info, dividend history
  data/raw/peers/<TICKER>.json    peer multiples (trailing P/E, P/B, EV/EBIT)
  data/raw/market.json            valuation-date market snapshot (^TNX, prices)

Valuation date is stamped at fetch time.
Usage: python scripts/fetch_data.py
"""
import json
import sys
import time
from datetime import date
from pathlib import Path

import yfinance as yf

ROOT = Path(__file__).resolve().parent.parent
RAW = ROOT / "data" / "raw"
PEERS_DIR = RAW / "peers"
RAW.mkdir(parents=True, exist_ok=True)
PEERS_DIR.mkdir(parents=True, exist_ok=True)

TICKERS = ["NVDA", "AMD", "MU", "AAPL", "META", "GOOG"]

# Comparable-company sets used for the relative-valuation multiples.
# Median peer multiple x company fundamental -> indicated value.
PEERS = {
    "NVDA": ["AMD", "AVGO", "QCOM", "TXN", "AMAT", "INTC"],
    "AMD": ["NVDA", "AVGO", "QCOM", "TXN", "AMAT", "INTC"],
    "MU": ["INTC", "QCOM", "TXN", "AMAT", "WDC", "STX"],
    "AAPL": ["MSFT", "DELL", "HPQ", "ORCL", "CSCO"],
    "META": ["GOOG", "PINS", "SNAP", "RDDT", "MSFT"],
    "GOOG": ["META", "MSFT", "AMZN", "PINS", "ORCL"],
}

INFO_KEYS = [
    "longName", "sector", "industry", "currency",
    "currentPrice", "regularMarketPrice", "previousClose",
    "marketCap", "sharesOutstanding", "floatShares",
    "beta", "trailingPE", "forwardPE", "pegRatio",
    "dividendRate", "dividendYield",
    "trailingAnnualDividendRate", "trailingAnnualDividendYield",
    "trailingEps", "forwardEps", "bookValue", "priceToBook",
    "enterpriseValue", "enterpriseToEbitda",
    "totalDebt", "totalCash", "ebitda",
    "returnOnEquity", "returnOnAssets", "profitMargins",
]

PEER_INFO_KEYS = [
    "longName", "sector", "industry", "currency",
    "currentPrice", "marketCap", "trailingPE", "forwardPE",
    "priceToBook", "enterpriseValue", "trailingEps",
]


def df_to_records(df):
    if df is None or df.empty:
        return {}
    out = {}
    for col in df.columns:
        key = str(col)[:10]
        vals = {}
        for idx, v in df[col].items():
            try:
                vals[str(idx)] = None if v != v else float(v)
            except Exception:
                vals[str(idx)] = None
        out[key] = vals
    return out


def annual_ebit(tk):
    """Latest annual EBIT (fallback: operating income), raw dollars."""
    try:
        fin = tk.financials
        if fin is None or fin.empty:
            return None
        col = fin.columns[0]
        for row in ["EBIT", "Operating Income"]:
            if row in fin.index:
                v = fin.loc[row, col]
                if v == v:
                    return float(v)
    except Exception:
        pass
    return None


def fetch_company(t):
    print(f"--- {t} ---", flush=True)
    tk = yf.Ticker(t)
    info = tk.info or {}
    info_sel = {k: info.get(k) for k in INFO_KEYS}
    try:
        hist = tk.history(period="5d")
        last_close = float(hist["Close"].iloc[-1]) if not hist.empty else None
    except Exception as e:
        print(f"  history failed: {e}")
        last_close = None
    try:
        divs = tk.dividends
        if divs is not None and not divs.empty:
            div_hist = [(str(ts.date()), float(val))
                        for ts, val in zip(divs.index, divs.values)]
        else:
            div_hist = []
    except Exception as e:
        print(f"  dividends failed: {e}")
        div_hist = []

    data = {
        "ticker": t,
        "valuation_date": str(date.today()),
        "info": info_sel,
        "lastClose5d": last_close,
        "financials": df_to_records(tk.financials),
        "balance_sheet": df_to_records(tk.balance_sheet),
        "cashflow": df_to_records(tk.cashflow),
        "dividends": div_hist,
    }
    try:
        bs = tk.balance_sheet
        for row in ["Ordinary Shares Number", "Share Issued", "Total Shares Outstanding"]:
            if row in bs.index:
                data["dilutedShares"] = float(bs.loc[row].iloc[0])
                break
    except Exception as e:
        print(f"  shares row failed: {e}")
    return data


def fetch_peer(t):
    """Lightweight pull: multiples + latest annual EBIT for EV/EBIT."""
    tk = yf.Ticker(t)
    info = tk.info or {}
    return {
        "ticker": t,
        "info": {k: info.get(k) for k in PEER_INFO_KEYS},
        "ebit": annual_ebit(tk),
    }


def main():
    failures = []
    for t in TICKERS:
        for attempt in range(3):
            try:
                (RAW / f"{t}.json").write_text(
                    json.dumps(fetch_company(t), indent=1))
                print(f"  saved {t}.json")
                break
            except Exception as e:
                print(f"  attempt {attempt+1} failed: {e}", flush=True)
                time.sleep(3)
        else:
            failures.append(t)

    # peers (unique set across all companies)
    all_peers = sorted({p for lst in PEERS.values() for p in lst})
    peer_data = {}
    for p in all_peers:
        for attempt in range(3):
            try:
                peer_data[p] = fetch_peer(p)
                print(f"  peer {p} ok")
                break
            except Exception as e:
                print(f"  peer {p} attempt {attempt+1} failed: {e}", flush=True)
                time.sleep(3)
        else:
            failures.append(f"peer:{p}")
    for t in TICKERS:
        (PEERS_DIR / f"{t}.json").write_text(json.dumps(
            {"ticker": t, "peers": PEERS[t],
             "data": {p: peer_data[p] for p in PEERS[t] if p in peer_data}},
            indent=1))

    # market snapshot: risk-free rate + company closes
    try:
        tnx = yf.Ticker("^TNX").history(period="5d")
        rf = float(tnx["Close"].iloc[-1]) / 100 if not tnx.empty else None
    except Exception as e:
        print(f"  ^TNX failed: {e}")
        rf = None
    (RAW / "market.json").write_text(json.dumps({
        "valuation_date": str(date.today()),
        "risk_free_10y": rf,
        "source": "US 10Y Treasury yield (^TNX)",
    }, indent=1))
    print(f"  risk-free (10Y): {rf}")

    if failures:
        print("FAILED:", failures)
        sys.exit(1)


if __name__ == "__main__":
    main()
