#!/usr/bin/env python3
"""Fetch the S&P 500 constituent list from Wikipedia.

Saves data/sp500/constituents.json: [{symbol, yahoo_symbol, name,
sector, sub_industry, cik}]. Yahoo Finance uses '-' where Wikipedia
uses '.' (BRK.B -> BRK-B).

Re-run to refresh membership (adds/drops); the daily batch reads this
file, so membership refreshes with the batch's own schedule only if
this script is re-run. The batch job runs this first.
"""
import json
from io import StringIO
from pathlib import Path

import pandas as pd
import requests

ROOT = Path(__file__).resolve().parent.parent
OUT = ROOT / "data" / "sp500"
OUT.mkdir(parents=True, exist_ok=True)

URL = "https://en.wikipedia.org/wiki/List_of_S%26P_500_companies"
UA = ("Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 "
      "Chrome/120 Safari/537.36")


def main():
    html = requests.get(URL, headers={"User-Agent": UA}, timeout=30).text
    t = pd.read_html(StringIO(html))[0]
    rows = []
    for _, r in t.iterrows():
        sym = str(r["Symbol"]).strip()
        if not sym or sym.lower() == "nan":
            continue
        rows.append({
            "symbol": sym,
            "yahoo_symbol": sym.replace(".", "-"),
            "name": str(r["Security"]).strip(),
            "sector": str(r["GICS Sector"]).strip(),
            "sub_industry": str(r["GICS Sub-Industry"]).strip(),
            "cik": str(r["CIK"]).strip(),
        })
    (OUT / "constituents.json").write_text(json.dumps(rows, indent=1))
    print(f"wrote {len(rows)} constituents")
    from collections import Counter
    print(Counter(r["sector"] for r in rows))


if __name__ == "__main__":
    main()
