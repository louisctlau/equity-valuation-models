# Equity Valuation — 9 Models × 6 Mega-Caps

Valuation date: **2026-09-25** · Risk-free rate **5.18%** (US 10Y ^TNX) · ERP **4.5%** · Cost of equity via CAPM (β from Yahoo Finance).

Three valuation families, three models each. All assumptions are editable in `assumptions/`; re-run with `python scripts/run_all.py`.

## 1. Present value models (discounted at cost of equity)

- **1a. Constant-growth (Gordon) DDM:** V₀ = D₁/(kₑ−g). g capped at 5% — raw ROE × retention (e.g. AAPL 149%, NVDA 117%) is not sustainable forever.
- **1b. Two-stage DDM:** dividends grow at g₁ for 5 years (per-ticker assumption), then Gordon at 3% stable growth.
- **1c. FCFE model:** FCFE₀ = NI + D&A − capex − ΔWC + net borrowing (latest annual cash-flow statement); 5-year projection at per-ticker growth, Gordon terminal at 2.75%.

**Limitation stated upfront:** DDM values are tiny for low-payout growers (NVDA $0.52/yr, MU $0.53/yr) — the math is honest, the dividend policy is the constraint. AMD pays no dividend: both DDM models are N/A and FCFE carries the present-value leg.

## 2. Multiplier / relative value models

- **2a. P/E comps:** median peer trailing P/E × company TTM EPS. Peer sets in `assumptions/peers.json` (semis, large-cap tech, ad platforms).
- **2b. P/B comps:** median peer P/B × book value per share (statement equity / diluted shares).
- **2c. EV/EBITA:** median peer EV/EBIT × company EBIT (**assumption:** EBITA ≈ EBIT — amortization not disclosed separately), then equity = EV − debt + cash, per share.

**Stated caveats:** MU's TTM EPS ($44.19) is a cyclical peak — peer P/E × peak earnings overstates. AMD's book value is inflated by acquisition goodwill (Xilinx) — P/B comps overstate.

## 3. Asset-based models

- **3a. Book value:** statement equity / diluted shares.
- **3b. Liquidation:** cash 100%, receivables 85%, inventory 55%, other current 75%, PPE 50%, other non-current 40%, goodwill and intangibles 0% — less all liabilities, per share. **Assumption:** distressed-sale discounts are judgmental; AAPL's result is negative because buybacks have thinned equity below a haircut asset base — a real signal about downside protection, not a bug.
- **3c. Replacement cost:** current assets @1.0×, PPE @1.35×, other tangible non-current @1.15×, less liabilities. **Assumption:** construction-cost inflation premium is an estimate.

## Per-ticker results (US$/share)

### NVDA — market $225.07 · kₑ 15.16% (β 2.22) · dividend $0.52/yr

| Model | Value | vs market |
|---|---|---|
| 1a. Gordon DDM | $5.37 | -97.6% |
| 1b. Two-stage DDM | $6.96 | -96.9% |
| 1c. FCFE model | $61.18 | -72.8% |
| 2a. P/E comps | $334.28 | +48.5% |
| 2b. P/B comps | $94.23 | -58.1% |
| 2c. EV/EBITA | $310.47 | +37.9% |
| 3a. Book value | $6.47 | -97.1% |
| 3b. Liquidation | $2.87 | -98.7% |
| 3c. Replacement cost | $5.94 | -97.4% |

Model median: **$6.96** (-96.9% vs market) · range $2.87–$334.28.

### AMD — market $630.63 · kₑ 16.33% (β 2.48) · dividend $0.00/yr

| Model | Value | vs market |
|---|---|---|
| 1a. Gordon DDM | N/A | — |
| 1b. Two-stage DDM | N/A | — |
| 1c. FCFE model | $51.70 | -91.8% |
| 2a. P/E comps | $163.48 | -74.1% |
| 2b. P/B comps | $562.71 | -10.8% |
| 2c. EV/EBITA | $105.73 | -83.2% |
| 3a. Book value | $38.65 | -93.9% |
| 3b. Liquidation | $6.94 | -98.9% |
| 3c. Replacement cost | $14.02 | -97.8% |

Model median: **$51.70** (-91.8% vs market) · range $6.94–$562.71.

> DDM models not applicable: company pays no dividend.

### MU — market $1,082.28 · kₑ 15.18% (β 2.22) · dividend $0.53/yr

| Model | Value | vs market |
|---|---|---|
| 1a. Gordon DDM | $5.46 | -99.5% |
| 1b. Two-stage DDM | $6.33 | -99.4% |
| 1c. FCFE model | $2.10 | -99.8% |
| 2a. P/E comps | $1,852.39 | +71.2% |
| 2b. P/B comps | $680.62 | -37.1% |
| 2c. EV/EBITA | $355.74 | -67.1% |
| 3a. Book value | $48.28 | -95.5% |
| 3b. Liquidation | $15.88 | -98.5% |
| 3c. Replacement cost | $62.28 | -94.2% |

Model median: **$48.28** (-95.5% vs market) · range $2.10–$1,852.39.

### AAPL — market $341.07 · kₑ 10.07% (β 1.08) · dividend $1.06/yr

| Model | Value | vs market |
|---|---|---|
| 1a. Gordon DDM | $21.97 | -93.6% |
| 1b. Two-stage DDM | $18.29 | -94.6% |
| 1c. FCFE model | $94.22 | -72.4% |
| 2a. P/E comps | $251.32 | -26.3% |
| 2b. P/B comps | $41.79 | -87.7% |
| 2c. EV/EBITA | $204.33 | -40.1% |
| 3a. Book value | $4.99 | -98.5% |
| 3b. Liquidation | $-8.99 | -102.6% |
| 3c. Replacement cost | $7.81 | -97.7% |

Model median: **$31.88** (-90.7% vs market) · range $4.99–$251.32.

### META — market $751.66 · kₑ 10.78% (β 1.24) · dividend $2.10/yr

| Model | Value | vs market |
|---|---|---|
| 1a. Gordon DDM | $38.17 | -94.9% |
| 1b. Two-stage DDM | $45.29 | -94.0% |
| 1c. FCFE model | $265.09 | -64.7% |
| 2a. P/E comps | $842.72 | +12.1% |
| 2b. P/B comps | $575.52 | -23.4% |
| 2c. EV/EBITA | $983.49 | +30.8% |
| 3a. Book value | $85.88 | -88.6% |
| 3b. Liquidation | $21.92 | -97.1% |
| 3c. Replacement cost | $103.86 | -86.2% |

Model median: **$103.86** (-86.2% vs market) · range $21.92–$983.49.

### GOOG — market $341.08 · kₑ 10.70% (β 1.23) · dividend $0.86/yr

| Model | Value | vs market |
|---|---|---|
| 1a. Gordon DDM | $15.85 | -95.4% |
| 1b. Two-stage DDM | $21.07 | -93.8% |
| 1c. FCFE model | $142.06 | -58.4% |
| 2a. P/E comps | $564.88 | +65.6% |
| 2b. P/B comps | $230.40 | -32.4% |
| 2c. EV/EBITA | $303.34 | -11.1% |
| 3a. Book value | $34.35 | -89.9% |
| 3b. Liquidation | $12.40 | -96.4% |
| 3c. Replacement cost | $40.34 | -88.2% |

Model median: **$40.34** (-88.2% vs market) · range $12.40–$564.88.

## Cross-model read

- **Present-value models** (FCFE-led) sit well below market for all six — at a 5.18% risk-free rate and CAPM discount rates of 10–16%, the market is pricing growth/risk the models don't grant.
- **Multiples** mostly point the other way (P/E comps above market for NVDA, META, GOOG) — the market values these names like their peers, which are themselves richly priced.
- **Asset-based** values anchor the downside: $3–$104/share. Liquidation is the floor; for AAPL it is negative — equity holders rely entirely on franchise value.
- The honest conclusion is the **range**, not a point: e.g. NVDA $3–$334 across models (median ~$61 ex-distortions), AAPL −$9–$251. No single model is 'right'; the families disagree because they measure different things (cash distributions vs peer pricing vs asset claims).

## Re-run

```bash
python3 -m venv .venv && .venv/bin/pip install yfinance pandas numpy matplotlib
.venv/bin/python scripts/fetch_data.py  # refresh market data
.venv/bin/python scripts/run_all.py      # rebuild docs/
```

Data: Yahoo Finance via `yfinance` (statements, prices, dividends, peer multiples). No API key.