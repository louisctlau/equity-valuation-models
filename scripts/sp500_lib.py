"""Shared helpers for the S&P 500 valuation pipeline.

Maps current yfinance statement labels onto the engine names in
scripts/models.py (the study's raw files used an older yfinance label
style; the engine itself is untouched). Also holds the systematic
assumption rules for 500 names — no per-ticker files at this scale.
"""
import statistics
import warnings

warnings.filterwarnings("ignore")

# Engine name -> candidate current-yfinance labels, in preference order.
# Names not listed here match by space/case-insensitive equality.
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

INC_NAMES = ["Net Income", "EBIT", "Operating Income"]
BS_NAMES = ["Stockholders Equity", "Total Equity Gross Minority Interest",
            "Common Stock Equity", "Total Liabilities Net Minority Interest",
            "Total Assets", "Total Debt", "Cash And Cash Equivalents",
            "Cash Cash Equivalents And Short Term Investments",
            "Other Short Term Investments", "Accounts Receivable",
            "Receivables", "Net Accounts Receivable", "Inventory",
            "Other Current Assets", "Prepaid Assets", "Net PPE", "Goodwill",
            "Other Intangible Assets", "Goodwill And Other Intangible Assets",
            "Other Non Current Assets", "Investments And Advances",
            "Other Investments", "Current Assets", "Total Non Current Assets",
            "Ordinary Shares Number"]
CF_NAMES = ["Depreciation And Amortization",
            "Depreciation Amortization Depletion", "Capital Expenditure",
            "Change In Working Capital", "Issuance Of Debt",
            "Long Term Debt Issued", "Net Issuance Of Debt",
            "Repayment Of Debt", "Long Term Debt Payments"]

# Systematic assumption defaults (documented; v1, no per-ticker tuning).
GORDON_G = 0.05            # matches all 6 originals (capped at 5%)
STABLE_G = 0.03            # from global.json
TERMINAL_G = 0.0275        # from global.json
ERP = 0.045                # from global.json
DIV_G1_FALLBACK = 0.05
FCFE_G_FALLBACK = 0.08
DIV_G1_CAP = 0.18
FCFE_G_CAP = 0.20
SECTOR_MIN_COUNT = 5       # else fall back to index-wide median


def _norm(s):
    return "".join(str(s).split()).casefold()


def _num(v):
    try:
        if v is None or v != v:
            return None
        return float(v)
    except Exception:
        return None


def pick(row, *names):
    """row: {yfinance label: value}. First resolving engine name wins."""
    by_norm = {}
    for k, v in row.items():
        nv = _num(v)
        if nv is not None:
            by_norm.setdefault(_norm(k), nv)
    for n in names:
        for cand in ALIASES.get(n, [n]):
            v = by_norm.get(_norm(cand))
            if v is not None:
                return v
    return None


def map_statement(df, names):
    """DataFrame (rows=labels, cols=year-ends) -> {year: {engine: value}}."""
    if df is None or df.empty:
        return {}
    out = {}
    for col in df.columns:
        key = str(col)[:10]
        row = {str(k): v for k, v in df[col].items()}
        out[key] = {n: pick(row, n) for n in names}
    return out


def latest_mapped(mapped):
    """{year: {...}} -> (chosen_year, {engine: value, non-None only}).

    Takes the latest column with at least one resolved value. Yahoo
    sometimes serves a stub latest column (only share/EPS rows, e.g.
    FDS 2026-08-31, FERG 2025-12-31) ahead of full statements; taking
    the max column unconditionally kills those tickers. Falls back to
    the newest fully-populated column instead.
    """
    if not mapped:
        return None, {}
    for y in sorted(mapped.keys(), reverse=True):
        d = {k: v for k, v in mapped[y].items() if v is not None}
        if d:
            return y, d
    return sorted(mapped.keys())[-1], {}


def annual_dividend_sums(div_list):
    """[(date, value)] -> {calendar year: total}."""
    sums = {}
    for d, v in div_list:
        y = str(d)[:4]
        sums[y] = sums.get(y, 0.0) + v
    return sums


def cagr(first, last, intervals):
    if first is None or last is None or first <= 0 or last <= 0 or intervals <= 0:
        return None
    return (last / first) ** (1.0 / intervals) - 1.0


def div_g1_rule(div_list):
    """5y dividend CAGR clipped to [0, cap]; fallback if uncomputable."""
    sums = annual_dividend_sums(div_list)
    years = sorted(sums.keys())
    if len(years) < 2:
        return DIV_G1_FALLBACK, "fallback: <2 dividend years"
    window = years[-6:]  # up to 5 intervals
    g = cagr(sums[window[0]], sums[window[-1]], len(window) - 1)
    if g is None:
        return DIV_G1_FALLBACK, "fallback: non-positive dividend year"
    return max(0.0, min(g, DIV_G1_CAP)), f"5y div CAGR {g:.3f} clipped"


def median_or_none(vals):
    vals = [v for v in vals if v is not None and v > 0]
    return statistics.median(vals) if vals else None
