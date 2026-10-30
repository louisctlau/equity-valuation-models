#!/usr/bin/env python3
"""Build the S&P 500 valuation snapshot (daily batch).

Pass 1: per ticker, fetch yfinance statements/info/dividends/price,
map to the study's engine names, apply systematic assumptions, compute
Category 1 + 3 models via scripts/models.py. Results are written
incrementally to data/snapshot/snapshot_work/<TICKER>.json, so a rerun
resumes instead of restarting (rate-limit safety).

Pass 2: sector medians (GICS sector, from the snapshot's own info
multiples; index-wide median if a sector has < 5 valid names) and
Category 2 models per ticker.

Output: data/snapshot/latest.json (the app's only input) +
data/snapshot/manifest.json (run metadata) + data/snapshot/runs.csv.

Usage: python scripts/sp500_build_snapshot.py [--subset N] [--force]
       [--skip-constituents]   (constituent refresh is a separate step:
       run scripts/sp500_fetch_constituents.py first, or daily before this)
"""
import argparse
import csv
import json
import statistics
import sys
import time
from datetime import date, datetime
from pathlib import Path
from zoneinfo import ZoneInfo

sys.path.insert(0, str(Path(__file__).resolve().parent))
import warnings

warnings.filterwarnings("ignore")
import yfinance as yf

import sp500_lib as L
from models import (book_value, cost_of_equity, ddm_gordon, ddm_two_stage,
                    fcfe_base, fcfe_model, liquidation, replacement_cost,
                    shares_out)

ROOT = Path(__file__).resolve().parent.parent
SP = ROOT / "data" / "sp500"
SNAP = ROOT / "data" / "snapshot"
WORK = SNAP / "snapshot_work"
WORK.mkdir(parents=True, exist_ok=True)

SLEEP_BETWEEN = 0.5


def fetch_ticker(ysym):
    tk = yf.Ticker(ysym)
    inc = L.map_statement(tk.get_income_stmt(), L.INC_NAMES)
    bs = L.map_statement(tk.get_balance_sheet(), L.BS_NAMES)
    cf = L.map_statement(tk.get_cashflow(), L.CF_NAMES)
    info = tk.get_info() or {}
    divs = tk.dividends
    div_list = []
    if divs is not None and len(divs):
        div_list = [[str(d.date()), float(v)] for d, v in divs.items()]
    price = None
    try:
        hist = tk.history(period="5d")
        if hist is not None and not hist.empty:
            price = float(hist["Close"].iloc[-1])
    except Exception:
        pass
    if price is None:
        price = (info.get("currentPrice") or info.get("regularMarketPrice")
                 or info.get("previousClose"))
    return inc, bs, cf, info, div_list, price


def build_record(meta, inc, bs, cf, info, div_list, price, rf, glob):
    fy, inc_d = L.latest_mapped(inc)
    bs_y, bs_d = L.latest_mapped(bs)
    cf_y, cf_d = L.latest_mapped(cf)
    if fy is None or not inc_d or not bs_d:
        raise ValueError("missing latest statements")
    fallbacks_pre = []
    for label, chosen, m in (("income", fy, inc), ("balance sheet", bs_y, bs),
                             ("cash flow", cf_y, cf)):
        if m and chosen != sorted(m.keys())[-1]:
            fallbacks_pre.append(
                f"{label} uses {chosen}; latest column "
                f"{sorted(m.keys())[-1]} was empty in Yahoo's feed")
    raw = {"dividends": div_list,
           "dilutedShares": bs_d.get("Ordinary Shares Number")
                            or info.get("sharesOutstanding")}
    c = {"raw": raw, "info": info, "inc": inc_d, "bs": bs_d, "cf": cf_d}
    ke, beta = cost_of_equity(info, rf, L.ERP)
    sh = shares_out(c)
    d0 = sum(v for _, v in div_list[-4:]) if div_list else 0.0

    # Systematic assumptions.
    div_g1, div_note = L.div_g1_rule(div_list)
    # FCFE growth: 5y CAGR of the annual FCFE base.
    bases = {}
    for y in sorted(cf.keys()):
        ci = {k: v for k, v in inc.get(y, {}).items() if v is not None}
        cc = {k: v for k, v in cf.get(y, {}).items() if v is not None}
        if ci and cc:
            bases[y] = fcfe_base({"inc": ci, "cf": cc})
    byears = sorted(bases.keys())[-6:]
    fcfe_g, fcfe_note = L.FCFE_G_FALLBACK, "fallback"
    if len(byears) >= 2:
        g = L.cagr(bases[byears[0]], bases[byears[-1]], len(byears) - 1)
        if g is not None:
            fcfe_g, fcfe_note = max(0.0, min(g, L.FCFE_G_CAP)), "5y FCFE CAGR clipped"
        else:
            fcfe_note = "fallback: non-positive FCFE base year"

    models, notes = {}, []
    if d0 > 0:
        models["ddm_gordon"] = ddm_gordon(c, ke, L.GORDON_G)
        models["ddm_two_stage"] = ddm_two_stage(c, ke, div_g1, L.STABLE_G)
    else:
        models["ddm_gordon"] = None
        models["ddm_two_stage"] = None
        notes.append("DDM N/A: pays no dividend")
    models["fcfe"] = fcfe_model(c, ke, fcfe_g, L.TERMINAL_G, sh)
    models["book_value"] = book_value(c, sh)
    liq = liquidation(c, sh, glob["liquidation_schedule"])
    models["liquidation"] = liq["per_share"] if liq else None
    models["replacement_cost"] = replacement_cost(c, sh, glob["replacement_params"])

    equity = (bs_d.get("Stockholders Equity")
              or bs_d.get("Total Equity Gross Minority Interest")
              or bs_d.get("Common Stock Equity"))
    ebit = inc_d.get("EBIT") or inc_d.get("Operating Income")
    ev = info.get("enterpriseValue")
    fallbacks = list(fallbacks_pre)
    if "Total Liabilities Net Minority Interest" not in bs_d:
        fallbacks.append("liabilities via assets-minus-equity")
    if info.get("beta") is None:
        fallbacks.append("beta=1.0")
    if bs_d.get("Ordinary Shares Number") is None:
        fallbacks.append("shares via info sharesOutstanding")
    if cf_d.get("Issuance Of Debt") is None:
        fallbacks.append("debt issuance treated as 0 in FCFE base")

    return {
        "ticker": meta["symbol"], "yahoo_symbol": meta["yahoo_symbol"],
        "name": meta["name"], "sector": meta["sector"],
        "sub_industry": meta["sub_industry"],
        "price": price, "fy_end": fy, "beta": beta, "ke": ke, "rf": rf,
        "shares": sh, "dividend_ann": d0, "fcfe_base": fcfe_base(c),
        "assumptions": {"gordon_g": L.GORDON_G, "div_g1": div_g1,
                        "div_g1_note": div_note, "fcfe_g": fcfe_g,
                        "fcfe_g_note": fcfe_note, "stable_g": L.STABLE_G,
                        "terminal_g": L.TERMINAL_G, "erp": L.ERP},
        "cat2_inputs": {
            "eps": info.get("trailingEps"),
            "bvps": (equity / sh) if equity is not None and sh else None,
            "ebit": ebit,
            "equity": equity,
            "debt": bs_d.get("Total Debt") or info.get("totalDebt"),
            "cash": (bs_d.get("Cash And Cash Equivalents")
                     or bs_d.get("Cash Cash Equivalents And Short Term Investments")
                     or info.get("totalCash")),
            "trailingPE": info.get("trailingPE"),
            "priceToBook": info.get("priceToBook"),
            "ev_ebit": (ev / ebit) if ev and ebit and ebit > 0 else None,
        },
        "models": models, "notes": notes, "fallbacks": fallbacks,
    }


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--subset", type=int, default=0)
    ap.add_argument("--force", action="store_true")
    args = ap.parse_args()

    consts = json.loads((SP / "constituents.json").read_text())
    if args.subset:
        consts = consts[:args.subset]
    glob = json.loads((ROOT / "assumptions" / "global.json").read_text())
    today = str(date.today())

    try:
        tnx = yf.Ticker("^TNX").history(period="5d")
        rf = float(tnx["Close"].iloc[-1]) / 100 if not tnx.empty else None
    except Exception:
        rf = None
    if rf is None:
        rf = glob["risk_free_fallback"]
        print("WARN: ^TNX failed, using fallback rf", rf)
    print(f"rf={rf:.4%}  universe={len(consts)}  date={today}", flush=True)

    ok, failed = [], []
    for i, meta in enumerate(consts, 1):
        wpath = WORK / f"{meta['symbol']}.json"
        if (not args.force and wpath.exists()
                and json.loads(wpath.read_text()).get("snapshot_date") == today):
            ok.append(meta["symbol"])
            continue
        rec = None
        for attempt in range(3):
            try:
                inc, bs, cf, info, div_list, price = fetch_ticker(meta["yahoo_symbol"])
                rec = build_record(meta, inc, bs, cf, info, div_list, price, rf, glob)
                break
            except Exception as e:
                print(f"  {meta['symbol']} attempt {attempt+1}: {type(e).__name__} {str(e)[:100]}", flush=True)
                time.sleep(5 if attempt == 0 else 15)
        if rec is None:
            failed.append(meta["symbol"])
        else:
            rec["snapshot_date"] = today
            wpath.write_text(json.dumps(rec, indent=1))
            ok.append(meta["symbol"])
        if i % 50 == 0:
            print(f"  ...{i}/{len(consts)} ok={len(ok)} failed={len(failed)}", flush=True)
        time.sleep(SLEEP_BETWEEN)

    # Pass 2: sector medians + Category 2.
    records = {}
    for sym in ok:
        try:
            records[sym] = json.loads((WORK / f"{sym}.json").read_text())
        except Exception:
            pass
    by_sector = {}
    for r in records.values():
        by_sector.setdefault(r["sector"], []).append(r)

    def median_for(sector, key):
        vals = [r["cat2_inputs"][key] for r in by_sector.get(sector, [])]
        med = L.median_or_none(vals)
        n = len([v for v in vals if v is not None and v > 0])
        if med is None or n < L.SECTOR_MIN_COUNT:
            allv = [r["cat2_inputs"][key] for r in records.values()]
            med = L.median_or_none(allv)
            return med, "index"
        return med, "sector"

    medians = {}
    for sector in by_sector:
        medians[sector] = {}
        for key in ("trailingPE", "priceToBook", "ev_ebit"):
            med, src = median_for(sector, key)
            medians[sector][key] = {"value": med, "source": src}

    for r in records.values():
        ci, sh, med = r["cat2_inputs"], r["shares"], medians[r["sector"]]
        pe_m, pb_m, ev_m = med["trailingPE"]["value"], med["priceToBook"]["value"], med["ev_ebit"]["value"]
        eps, bvps = ci["eps"], ci["bvps"]
        r["models"]["pe_comps"] = (pe_m * eps) if (pe_m and eps and eps > 0) else None
        if not (pe_m and eps and eps > 0):
            r["notes"].append("P/E comps N/A: no valid sector median or EPS<=0")
        eq = ci["equity"]
        r["models"]["pb_comps"] = (pb_m * bvps) if (pb_m and eq and eq > 0 and sh) else None
        if not (pb_m and eq and eq > 0 and sh):
            r["notes"].append("P/B comps N/A: no valid sector median or equity<=0")
        ebit = ci["ebit"]
        if ev_m and ebit and ebit > 0 and sh:
            ev = ev_m * ebit
            r["models"]["ev_ebita"] = (ev - (ci["debt"] or 0) + (ci["cash"] or 0)) / sh
        else:
            r["models"]["ev_ebita"] = None
            r["notes"].append("EV/EBITA N/A: no valid sector median or EBIT<=0")
        r["sector_medians"] = medians[r["sector"]]

    model_keys = ["ddm_gordon", "ddm_two_stage", "fcfe", "pe_comps",
                  "pb_comps", "ev_ebita", "book_value", "liquidation",
                  "replacement_cost"]
    coverage = {k: sum(1 for r in records.values() if r["models"].get(k) is not None)
                for k in model_keys}
    manifest = {"snapshot_date": today,
                "snapshot_datetime":
                    datetime.now(ZoneInfo("America/Toronto")).isoformat(timespec="minutes"),
                "rf": rf, "erp": L.ERP,
                "universe": len(consts), "ok": len(records),
                "failed": failed, "coverage": coverage}
    (SNAP / "latest.json").write_text(json.dumps(
        {"manifest": manifest, "tickers": records}, indent=1))
    (SNAP / "manifest.json").write_text(json.dumps(manifest, indent=1))

    # Append today's per-ticker price/mean/median to the history file the
    # app's valuation-history chart reads. Re-running a date overwrites
    # that date instead of duplicating it.
    hist_path = SNAP / "history.json"
    hist = {"dates": [], "tickers": {}}
    if hist_path.exists():
        try:
            hist = json.loads(hist_path.read_text())
        except Exception:
            hist = {"dates": [], "tickers": {}}
    if today not in hist["dates"]:
        hist["dates"].append(today)
    for sym, r in records.items():
        vals = [v for v in r["models"].values() if v is not None]
        hist["tickers"].setdefault(sym, {})[today] = {
            "price": round(r["price"], 2) if r["price"] else None,
            "mean": round(statistics.mean(vals), 2) if vals else None,
            "median": round(statistics.median(vals), 2) if vals else None,
            "n": len(vals)}
    hist_path.write_text(json.dumps(hist, indent=1))
    runs = SNAP / "runs.csv"
    new = not runs.exists()
    with open(runs, "a", newline="") as f:
        w = csv.writer(f)
        if new:
            w.writerow(["date", "universe", "ok", "failed_n", "rf"])
        w.writerow([today, len(consts), len(records), len(failed), rf])
    print(f"DONE ok={len(records)} failed={len(failed)}")
    print("coverage:", coverage)
    if failed:
        print("failed:", failed)


if __name__ == "__main__":
    main()
