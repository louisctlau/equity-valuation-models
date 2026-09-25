"""Build the Excel valuation workbook: 9 formula-driven models x 6 companies.

Sheets: Summary | Assumptions | Peers | NVDA | AMD | MU | AAPL | META | GOOG
Every model value is a live Excel formula — change an assumption and the
workbook reprices. #N/A appears only where a model is genuinely not
applicable (DDM for non-dividend-payer AMD).

Usage: python scripts/build_workbook.py
"""
import json
from pathlib import Path

from openpyxl import Workbook
from openpyxl.styles import Font, PatternFill, Alignment, Border, Side
from openpyxl.utils import get_column_letter

ROOT = Path(__file__).resolve().parent.parent
TICKERS = ["NVDA", "AMD", "MU", "AAPL", "META", "GOOG"]
PEER_ORDER = {
    "NVDA": ["AMD", "AVGO", "QCOM", "TXN", "AMAT", "INTC"],
    "AMD": ["NVDA", "AVGO", "QCOM", "TXN", "AMAT", "INTC"],
    "MU": ["INTC", "QCOM", "TXN", "AMAT", "WDC", "STX"],
    "AAPL": ["MSFT", "DELL", "HPQ", "ORCL", "CSCO"],
    "META": ["GOOG", "PINS", "SNAP", "RDDT", "MSFT"],
    "GOOG": ["META", "MSFT", "AMZN", "PINS", "ORCL"],
}
ASSUMP_ROW = {t: 26 + i for i, t in enumerate(TICKERS)}  # per-ticker rows

HDR_FILL = PatternFill("solid", fgColor="1F3864")
HDR_FONT = Font(bold=True, color="FFFFFF", size=11)
SEC_FILL = PatternFill("solid", fgColor="D9E2F3")
SEC_FONT = Font(bold=True, size=11)
TITLE_FONT = Font(bold=True, size=14)
NOTE_FONT = Font(italic=True, color="595959", size=9)
THIN = Border(*[Side(style="thin", color="BFBFBF")] * 4)

F_MONEY = '#,##0'
F_SHARE = '$#,##0.00'
F_PCT = '0.00%'
F_MULT = '#,##0.0'


def style_header(ws, row, ncols):
    for c in range(1, ncols + 1):
        cell = ws.cell(row=row, column=c)
        cell.fill = HDR_FILL
        cell.font = HDR_FONT
        cell.alignment = Alignment(horizontal="center", vertical="center")


def section(ws, row, text, ncols=4):
    ws.merge_cells(start_row=row, start_column=1, end_row=row, end_column=ncols)
    c = ws.cell(row=row, column=1, value=text)
    c.fill = SEC_FILL
    c.font = SEC_FONT


def load_company_data():
    def get(row, *names):
        for n in names:
            v = row.get(n)
            if v is not None:
                return v
        return None

    out = {}
    for t in TICKERS:
        d = json.loads((ROOT / "data" / "raw" / f"{t}.json").read_text())
        inc = d["financials"][sorted(d["financials"])[-1]]
        bs = d["balance_sheet"][sorted(d["balance_sheet"])[-1]]
        cf = d["cashflow"][sorted(d["cashflow"])[-1]]
        i = d["info"]
        divs = d.get("dividends") or []
        te = get(bs, "Stockholders Equity", "Total Equity Gross Minority Interest",
                 "Common Stock Equity")
        ta = get(bs, "Total Assets")
        tl = get(bs, "Total Liabilities Net Minority Interest") or (ta - te)
        iss = get(cf, "Issuance Of Debt", "Long Term Debt Issued",
                  "Net Issuance Of Debt") or 0
        rep = get(cf, "Repayment Of Debt", "Long Term Debt Payments") or 0
        M = 1e6
        out[t] = {
            "price": d.get("lastClose5d") or i.get("currentPrice"),
            "beta": i.get("beta") or 1.0,
            "div": sum(v for _, v in divs[-4:]) if divs else 0.0,
            "shares": (d.get("dilutedShares") or bs.get("Ordinary Shares Number")
                       or i.get("sharesOutstanding")) / M,
            "ni": (get(inc, "Net Income") or 0) / M,
            "da": (get(cf, "Depreciation And Amortization",
                        "Depreciation Amortization Depletion") or 0) / M,
            "capex": (get(cf, "Capital Expenditure") or 0) / M,
            "wc": (get(cf, "Change In Working Capital") or 0) / M,
            "net_borrow": (iss + rep) / M,
            "eps": i.get("trailingEps"),
            "equity": te / M,
            "debt": (get(bs, "Total Debt") or i.get("totalDebt") or 0) / M,
            # EV-bridge cash: engine definition = cash & equivalents only
            # (ST investments are a separate liquidation bucket)
            "cash_ev": ((get(bs, "Cash And Cash Equivalents",
                             "Cash Cash Equivalents And Short Term Investments")
                         or i.get("totalCash") or 0)) / M,
            "cash": ((get(bs, "Cash And Cash Equivalents") or 0)
                     + (get(bs, "Other Short Term Investments") or 0)) / M,
            "ebit": (get(inc, "EBIT", "Operating Income") or 0) / M,
            "ta": ta / M, "tl": tl / M,
            "bs_cash": (get(bs, "Cash And Cash Equivalents") or 0) / M,
            "bs_stinv": (get(bs, "Other Short Term Investments") or 0) / M,
            "recv": (get(bs, "Accounts Receivable", "Receivables") or 0) / M,
            "inv": (get(bs, "Inventory") or 0) / M,
            "oca": (get(bs, "Other Current Assets") or 0) / M,
            "ppe": (get(bs, "Net PPE") or 0) / M,
            "gw": (get(bs, "Goodwill") or 0) / M,
            "intan": (get(bs, "Other Intangible Assets") or 0) / M,
            "onca": (get(bs, "Other Non Current Assets") or 0) / M,
            "ca": (get(bs, "Current Assets") or 0) / M,
            "nca": (get(bs, "Total Non Current Assets") or 0) / M,
        }
    return out


def load_peer_data():
    peers = {}
    for t in TICKERS:
        d = json.loads((ROOT / "data" / "raw" / "peers" / f"{t}.json").read_text())
        for p, pd_ in d["data"].items():
            if p in peers:
                continue
            info = pd_["info"]
            pe = info.get("trailingPE")
            pb = info.get("priceToBook")
            ev, ebit = info.get("enterpriseValue"), pd_.get("ebit")
            peers[p] = {
                "pe": pe if pe and pe > 0 else None,
                "pb": pb if pb and pb > 0 else None,
                "ev_ebit": (ev / ebit) if ev and ebit and ebit > 0 else None,
            }
    return peers


def build_assumptions(ws):
    ws["A1"] = "Assumptions — edit the blue cells to reprice every model"
    ws["A1"].font = TITLE_FONT
    ws.column_dimensions["A"].width = 38
    ws.column_dimensions["B"].width = 18
    ws.column_dimensions["C"].width = 18
    ws.column_dimensions["D"].width = 16
    ws.column_dimensions["E"].width = 60
    for c in ["B2", "B3", "B4", "B5", "B6", "B9", "B10", "B11", "B12", "B13",
              "B14", "B15", "B16", "B17", "B20", "B21", "B22",
              "B25", "C25", "D25", "B26", "C26", "D26", "B27", "C27", "D27",
              "B28", "C28", "D28", "B29", "C29", "D29", "B30", "C30", "D30"]:
        ws[c].fill = PatternFill("solid", fgColor="DDEBF7")
    section(ws, 1, "", 5)
    ws["A1"] = "Assumptions — edit the shaded cells to reprice every model"
    ws["A1"].font = TITLE_FONT
    rows = [("Risk-free rate (US 10Y, 2026-09-25)", 0.05184, F_PCT,
             "FRED ^TNX at fetch"),
            ("Equity risk premium", 0.045, F_PCT, "Assumption"),
            ("FCFE terminal growth", 0.0275, F_PCT, "Long-run nominal GDP proxy"),
            ("DDM stage-2 stable growth", 0.03, F_PCT, "Assumption"),
            ("Gordon growth cap", 0.05, F_PCT,
             "ROE x retention exceeds this for all payers; capped")]
    for k, (label, val, fmt, note) in enumerate(rows):
        r = 2 + k
        ws.cell(row=r, column=1, value=label)
        c = ws.cell(row=r, column=2, value=val)
        c.number_format = fmt
        ws.cell(row=r, column=5, value=note).font = NOTE_FONT
    section(ws, 8, "Liquidation — recovery rates (distressed sale)", 5)
    sched = [("Cash & equivalents", 1.0), ("Short-term investments", 1.0),
             ("Receivables", 0.85), ("Inventory", 0.55),
             ("Other current assets", 0.75), ("Net PPE", 0.50),
             ("Other non-current assets", 0.40), ("Goodwill", 0.0),
             ("Intangible assets", 0.0)]
    for k, (label, val) in enumerate(sched):
        r = 9 + k
        ws.cell(row=r, column=1, value=label)
        ws.cell(row=r, column=2, value=val).number_format = F_PCT
    ws.cell(row=9, column=5, value="Judgmental — sensitivity-test these").font = NOTE_FONT
    section(ws, 19, "Replacement cost — restatement multiples", 5)
    repl = [("Current assets", 1.0), ("Net PPE", 1.35),
            ("Other tangible non-current", 1.15)]
    for k, (label, val) in enumerate(repl):
        r = 20 + k
        ws.cell(row=r, column=1, value=label)
        ws.cell(row=r, column=2, value=val).number_format = "0.00"
    ws.cell(row=20, column=5,
            value="Construction-cost inflation estimate").font = NOTE_FONT
    for c in range(1, 6):
        cell = ws.cell(row=24, column=c)
        cell.fill = SEC_FILL
        cell.font = SEC_FONT
    ws.cell(row=24, column=1, value="Per-ticker growth assumptions")
    for j, h in enumerate(["Ticker", "Dividend g1 (2-stage)", "FCFE 5-yr g",
                           "Gordon g", "Rationale"]):
        c = ws.cell(row=25, column=1 + j, value=h)
    style_header(ws, 25, 5)
    trows = [
        ("NVDA", 0.15, 0.18, 0.05, "Tiny base, recent raises; AI supercycle"),
        ("AMD", None, 0.22, 0.05, "No dividend — DDM N/A; AI share gains"),
        ("MU", 0.12, 0.15, 0.05, "Raised to $0.15/q; memory recovery"),
        ("AAPL", 0.07, 0.08, 0.05, "Historical raise pace; mature grower"),
        ("META", 0.15, 0.12, 0.05, "Initiated 2024, fast off small base"),
        ("GOOG", 0.18, 0.11, 0.05, "Initiated 2024, already raised"),
    ]
    for k, (t, g1, gf, gg, note) in enumerate(trows):
        r = 26 + k
        ws.cell(row=r, column=1, value=t).font = Font(bold=True)
        if g1 is not None:
            ws.cell(row=r, column=2, value=g1).number_format = F_PCT
        else:
            ws.cell(row=r, column=2, value="N/A")
        ws.cell(row=r, column=3, value=gf).number_format = F_PCT
        ws.cell(row=r, column=4, value=gg).number_format = F_PCT
        ws.cell(row=r, column=5, value=note).font = NOTE_FONT


def build_peers(ws, peer_data):
    ws["A1"] = "Comparable-company multiples (Yahoo Finance, 2026-09-25)"
    ws["A1"].font = TITLE_FONT
    for j, h in enumerate(["Subject", "Peer", "Trailing P/E", "P/B",
                           "EV/EBIT"]):
        ws.cell(row=2, column=1 + j, value=h)
    style_header(ws, 2, 5)
    ws.column_dimensions["A"].width = 12
    ws.column_dimensions["B"].width = 12
    for col in "CDE":
        ws.column_dimensions[col].width = 16
    r = 3
    medrows = {}
    for t in TICKERS:
        start = r
        for p in PEER_ORDER[t]:
            d = peer_data[p]
            ws.cell(row=r, column=1, value=t)
            ws.cell(row=r, column=2, value=p).font = Font(bold=True)
            if d["pe"]:
                ws.cell(row=r, column=3, value=d["pe"]).number_format = F_MULT
            if d["pb"]:
                ws.cell(row=r, column=4, value=d["pb"]).number_format = F_MULT
            if d["ev_ebit"]:
                ws.cell(row=r, column=5, value=d["ev_ebit"]).number_format = F_MULT
            r += 1
        ws.cell(row=r, column=2, value=f"{t} median").font = Font(bold=True)
        for j, col in enumerate("CDE"):
            ws.cell(row=r, column=3 + j,
                    value=f"=MEDIAN({col}{start}:{col}{r-1})").number_format = F_MULT
            ws.cell(row=r, column=3 + j).font = Font(bold=True)
        medrows[t] = r
        r += 2
    ws.cell(row=r, column=1,
            value="Blanks = negative or unavailable multiple (excluded from median)").font = NOTE_FONT
    return medrows


def build_company(ws, t, d, medrow, arow):
    ws.sheet_properties.tabColor = "1F3864"
    ws["A1"] = f"{t} — equity valuation (9 models)"
    ws["A1"].font = TITLE_FONT
    ws["A2"] = ("Valuation date 2026-09-25 · $ millions except per-share · "
                "blue cells are live formulas")
    ws["A2"].font = NOTE_FONT
    for col, w in [("A", 34), ("B", 20), ("C", 20), ("D", 22), ("E", 52)]:
        ws.column_dimensions[col].width = w

    def inp(row, label, value, fmt, note=""):
        ws.cell(row=row, column=1, value=label)
        c = ws.cell(row=row, column=2, value=value)
        c.number_format = fmt
        if note:
            ws.cell(row=row, column=5, value=note).font = NOTE_FONT
        return c

    section(ws, 4, "INPUTS — market data & latest annual statements")
    inp(5, "Market price ($/share)", d["price"], F_SHARE, "Yahoo Finance 2026-09-25")
    inp(6, "Beta", d["beta"], "0.00", "Yahoo Finance")
    ws.cell(row=7, column=1, value="Cost of equity ke (CAPM)")
    ws.cell(row=7, column=2,
            value="=Assumptions!$B$2+B6*Assumptions!$B$3").number_format = F_PCT
    ws.cell(row=7, column=5, value="rf + β × ERP").font = NOTE_FONT
    inp(8, "Annualized dividend D0 ($/share)", d["div"], F_SHARE,
        "Sum of last 4 declared dividends" if d["div"] else "Pays no dividend")
    inp(9, "Diluted shares (mm)", d["shares"], F_MONEY, "Balance sheet")
    inp(10, "Net income", d["ni"], F_MONEY)
    inp(11, "Depreciation & amortization", d["da"], F_MONEY)
    inp(12, "Capital expenditure", d["capex"], F_MONEY, "Negative = outflow")
    inp(13, "Change in working capital", d["wc"], F_MONEY, "Cash-flow impact")
    inp(14, "Net borrowing", d["net_borrow"], F_MONEY, "Issued − repaid")
    ws.cell(row=15, column=1, value="FCFE0 (computed)")
    ws.cell(row=15, column=2, value="=SUM(B10:B14)").number_format = F_MONEY
    ws.cell(row=15, column=5,
            value="NI + D&A + capex + ΔWC + net borrowing").font = NOTE_FONT
    inp(16, "TTM EPS ($/share)", d["eps"], F_SHARE, "Yahoo Finance")
    inp(17, "Total stockholders' equity", d["equity"], F_MONEY)
    ws.cell(row=18, column=1, value="Book value per share (computed)")
    ws.cell(row=18, column=2, value="=B17/B9").number_format = F_SHARE
    inp(19, "Total debt", d["debt"], F_MONEY)
    inp(20, "Cash & cash equivalents", d["cash_ev"], F_MONEY,
        "EV bridge: excludes ST investments (own liquidation bucket)")
    inp(21, "EBIT", d["ebit"], F_MONEY, "EBITA ≈ EBIT (amort. undisclosed)")
    inp(22, "Total assets", d["ta"], F_MONEY)
    inp(23, "Total liabilities", d["tl"], F_MONEY, "TA − equity where undisclosed")
    bsrows = [(24, "Cash & cash equivalents", "bs_cash"),
              (25, "Other short-term investments", "bs_stinv"),
              (26, "Receivables", "recv"), (27, "Inventory", "inv"),
              (28, "Other current assets", "oca"), (29, "Net PPE", "ppe"),
              (30, "Goodwill", "gw"), (31, "Other intangible assets", "intan"),
              (32, "Other non-current assets", "onca"),
              (33, "Current assets (total)", "ca"),
              (34, "Total non-current assets", "nca")]
    for row, label, key in bsrows:
        inp(row, label, d[key], F_MONEY)
    ws.cell(row=35, column=1, value="Peer median trailing P/E")
    ws.cell(row=35, column=2, value=f"=Peers!C{medrow}").number_format = F_MULT
    ws.cell(row=36, column=1, value="Peer median P/B")
    ws.cell(row=36, column=2, value=f"=Peers!D{medrow}").number_format = F_MULT
    ws.cell(row=37, column=1, value="Peer median EV/EBIT")
    ws.cell(row=37, column=2, value=f"=Peers!E{medrow}").number_format = F_MULT
    ws.cell(row=38, column=1, value="Dividend growth g1 (2-stage)")
    ws.cell(row=38, column=2, value=f"=Assumptions!B{arow}").number_format = F_PCT
    ws.cell(row=39, column=1, value="FCFE 5-yr growth")
    ws.cell(row=39, column=2, value=f"=Assumptions!C{arow}").number_format = F_PCT
    ws.cell(row=40, column=1, value="Gordon growth g")
    ws.cell(row=40, column=2, value=f"=Assumptions!D{arow}").number_format = F_PCT

    def model_value(row, label, formula, note=""):
        ws.cell(row=row, column=1, value=label).font = Font(bold=True)
        ws.cell(row=row, column=2, value=formula).number_format = F_SHARE
        if note:
            ws.cell(row=row, column=5, value=note).font = NOTE_FONT

    # 1a Gordon
    section(ws, 42, "1a. CONSTANT-GROWTH (GORDON) DDM — V0 = D1/(ke−g)")
    ws.cell(row=43, column=1, value="D1 = D0×(1+g)")
    ws.cell(row=43, column=2, value="=B8*(1+B40)").number_format = F_SHARE
    model_value(44, "Indicated value", "=IF(B8=0,NA(),B43/(B7-B40))",
                "N/A when the company pays no dividend")
    # 1b two-stage
    section(ws, 46, "1b. TWO-STAGE DDM — 5 yrs at g1, then 3% stable")
    for j, h in enumerate(["Year", "Dividend", "PV of dividend"]):
        ws.cell(row=47, column=1 + j, value=h).font = Font(bold=True)
    for k in range(5):
        r = 48 + k
        ws.cell(row=r, column=1, value=k + 1)
        ws.cell(row=r, column=2,
                value=f"=B$8*(1+B$38)^A{r}").number_format = F_SHARE
        ws.cell(row=r, column=3,
                value=f"=B{r}/(1+B$7)^A{r}").number_format = F_SHARE
    ws.cell(row=53, column=1, value="Terminal value at yr 5")
    ws.cell(row=53, column=2,
            value="=B52*(1+Assumptions!$B$5)/(B$7-Assumptions!$B$5)").number_format = F_MONEY
    ws.cell(row=54, column=1, value="PV of terminal")
    ws.cell(row=54, column=2, value="=B53/(1+B$7)^5").number_format = F_MONEY
    model_value(55, "Indicated value", "=IF(B$8=0,NA(),SUM(C48:C52)+B54)")
    # 1c FCFE
    section(ws, 57, "1c. FCFE MODEL — 5-yr projection + Gordon terminal")
    for j, h in enumerate(["Year", "FCFE", "PV of FCFE"]):
        ws.cell(row=58, column=1 + j, value=h).font = Font(bold=True)
    for k in range(5):
        r = 59 + k
        ws.cell(row=r, column=1, value=k + 1)
        ws.cell(row=r, column=2,
                value=f"=B$15*(1+B$39)^A{r}").number_format = F_MONEY
        ws.cell(row=r, column=3,
                value=f"=B{r}/(1+B$7)^A{r}").number_format = F_MONEY
    ws.cell(row=64, column=1, value="Terminal value at yr 5")
    ws.cell(row=64, column=2,
            value="=B63*(1+Assumptions!$B$4)/(B$7-Assumptions!$B$4)").number_format = F_MONEY
    ws.cell(row=65, column=1, value="PV of terminal")
    ws.cell(row=65, column=2,
            value="=B64/(1+B$7)^5").number_format = F_MONEY
    ws.cell(row=66, column=1, value="Equity value")
    ws.cell(row=66, column=2, value="=SUM(C59:C63)+B65").number_format = F_MONEY
    model_value(67, "Indicated value per share", "=B66/B$9")
    # 2a / 2b
    section(ws, 68, "2. MULTIPLES — peer medians × company fundamental")
    model_value(69, "2a. P/E comps", "=B35*B16",
                "Peer median P/E × TTM EPS")
    model_value(70, "2b. P/B comps", "=B36*B18",
                "Peer median P/B × book value/share")
    # 2c EV/EBITA
    ws.cell(row=72, column=1,
            value="2c. EV/EBITA (EBITA ≈ EBIT)").font = Font(bold=True)
    ws.cell(row=73, column=1, value="Implied enterprise value")
    ws.cell(row=73, column=2, value="=B37*B21").number_format = F_MONEY
    ws.cell(row=74, column=1, value="Less: total debt")
    ws.cell(row=74, column=2, value="=B19").number_format = F_MONEY
    ws.cell(row=75, column=1, value="Add: cash")
    ws.cell(row=75, column=2, value="=B20").number_format = F_MONEY
    model_value(76, "Indicated value per share", "=(B73-B74+B75)/B9")
    # 3a
    section(ws, 77, "3a. BOOK VALUE")
    model_value(78, "Indicated value", "=B18", "Equity ÷ shares")
    # 3b liquidation
    section(ws, 80, "3b. LIQUIDATION — recovery schedule x gross assets")
    for j, h in enumerate(["Asset", "Gross", "Recovery", "Recoverable"]):
        ws.cell(row=81, column=1 + j, value=h).font = Font(bold=True)
    liq = [(82, "=B24", "Assumptions!$B$9"), (83, "=B25", "Assumptions!$B$10"),
           (84, "=B26", "Assumptions!$B$11"), (85, "=B27", "Assumptions!$B$12"),
           (86, "=B28", "Assumptions!$B$13"), (87, "=B29", "Assumptions!$B$14"),
           (88, "=B30", "Assumptions!$B$16"), (89, "=B31", "Assumptions!$B$17"),
           (90, "=B32", "Assumptions!$B$15")]
    labels = ["Cash & equivalents", "ST investments", "Receivables",
              "Inventory", "Other current", "Net PPE", "Goodwill",
              "Intangibles", "Other non-current"]
    for (r, gross, rec), lab in zip(liq, labels):
        ws.cell(row=r, column=1, value=lab)
        ws.cell(row=r, column=2, value=gross).number_format = F_MONEY
        ws.cell(row=r, column=3, value=f"={rec}").number_format = F_PCT
        ws.cell(row=r, column=4, value=f"=B{r}*C{r}").number_format = F_MONEY
    ws.cell(row=91, column=1, value="Total recoverable").font = Font(bold=True)
    ws.cell(row=91, column=4, value="=SUM(D82:D90)").number_format = F_MONEY
    ws.cell(row=92, column=1, value="Less: total liabilities")
    ws.cell(row=92, column=4, value="=B23").number_format = F_MONEY
    ws.cell(row=93, column=1,
            value="Indicated value per share").font = Font(bold=True)
    ws.cell(row=93, column=2, value="=(D91-D92)/B9").number_format = F_SHARE
    ws.cell(row=93, column=5, value="Floor value; can be negative").font = NOTE_FONT
    # 3c replacement
    section(ws, 94, "3c. REPLACEMENT COST — tangible assets restated")
    ws.cell(row=95, column=1, value="Current assets × 1.00")
    ws.cell(row=95, column=2, value="=B33*Assumptions!$B$20").number_format = F_MONEY
    ws.cell(row=96, column=1, value="Net PPE × 1.35")
    ws.cell(row=96, column=2, value="=B29*Assumptions!$B$21").number_format = F_MONEY
    ws.cell(row=97, column=1, value="Other tangible non-current × 1.15")
    ws.cell(row=97, column=2,
            value="=MAX(B34-B29-B30-B31,0)*Assumptions!$B$22").number_format = F_MONEY
    ws.cell(row=98, column=1, value="Total replacement assets").font = Font(bold=True)
    ws.cell(row=98, column=2, value="=SUM(B95:B97)").number_format = F_MONEY
    ws.cell(row=99, column=1, value="Less: total liabilities")
    ws.cell(row=99, column=2, value="=B23").number_format = F_MONEY
    model_value(100, "Indicated value per share", "=(B98-B99)/B9",
                "Construction-cost inflation is an estimate")


VALUE_CELLS = {"1a": "B44", "1b": "B55", "1c": "B67", "2a": "B69",
               "2b": "B70", "2c": "B76", "3a": "B78", "3b": "B93", "3c": "B100"}
MODEL_LABELS = ["1a. Gordon DDM", "1b. Two-stage DDM", "1c. FCFE model",
                "2a. P/E comps", "2b. P/B comps", "2c. EV/EBITA",
                "3a. Book value", "3b. Liquidation", "3c. Replacement cost"]


def build_summary(ws):
    ws["A1"] = "Summary — indicated value per share (US$), all formulas live"
    ws["A1"].font = TITLE_FONT
    ws.column_dimensions["A"].width = 24
    for j, t in enumerate(TICKERS):
        ws.column_dimensions[get_column_letter(2 + j)].width = 16
        ws.cell(row=2, column=2 + j, value=t).font = Font(bold=True)
    ws.cell(row=2, column=1, value="Model").font = Font(bold=True)
    style_header(ws, 2, 7)
    keys = ["1a", "1b", "1c", "2a", "2b", "2c", "3a", "3b", "3c"]
    for k, (key, label) in enumerate(zip(keys, MODEL_LABELS)):
        r = 3 + k
        ws.cell(row=r, column=1, value=label)
        for j, t in enumerate(TICKERS):
            ws.cell(row=r, column=2 + j,
                    value=f"=IF(ISNA({t}!{VALUE_CELLS[key]}),\"\","
                          f"{t}!{VALUE_CELLS[key]})").number_format = F_SHARE
    r = 12
    ws.cell(row=r, column=1, value="Market price").font = Font(bold=True)
    for j, t in enumerate(TICKERS):
        ws.cell(row=r, column=2 + j, value=f"={t}!B5").number_format = F_SHARE
    r = 13
    ws.cell(row=r, column=1, value="Median of models").font = Font(bold=True)
    for j in range(len(TICKERS)):
        col = get_column_letter(2 + j)
        ws.cell(row=r, column=2 + j,
                value=f"=MEDIAN({col}3:{col}11)").number_format = F_SHARE
    r = 14
    ws.cell(row=r, column=1, value="Implied upside (median)").font = Font(bold=True)
    for j in range(len(TICKERS)):
        col = get_column_letter(2 + j)
        ws.cell(row=r, column=2 + j,
                value=f"=IF({col}12=0,\"\",{col}13/{col}12-1)").number_format = F_PCT
    ws.cell(row=16, column=1,
            value="N/A (AMD dividend models) excluded from medians").font = NOTE_FONT


def main():
    co = load_company_data()
    peer_data = load_peer_data()
    wb = Workbook()
    ws = wb.active
    ws.title = "Summary"
    build_summary(ws)
    wa = wb.create_sheet("Assumptions")
    build_assumptions(wa)
    wp = wb.create_sheet("Peers")
    medrows = build_peers(wp, peer_data)
    for t in TICKERS:
        wc = wb.create_sheet(t)
        build_company(wc, t, co[t], medrows[t], ASSUMP_ROW[t])
    out = Path.home() / "workspace" / "your_files" / "equity-valuation-models"
    out.mkdir(parents=True, exist_ok=True)
    path = out / "Equity Valuation Models \u2014 6 Mega-Caps.xlsx"
    wb.save(path)
    print("saved", path)


if __name__ == "__main__":
    main()
