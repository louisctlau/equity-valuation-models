# Changelog — S&P 500 Valuation

## 2026-10-25 — Distinct chart markers

- The valuation range chart now gives every model its own marker and colour:
  Gordon DDM a yellow star, two-stage DDM a blue square, FCFE a red triangle,
  P/E comps a green circle, P/B comps a purple diamond, EV/EBITA an orange
  pentagon, book value a cyan hexagon, liquidation a magenta X, replacement
  cost a brown down-triangle. Previously every model plotted as the same dot.

## 2026-10-25 — Title renamed

- App title changed to "S&P 500 - Equity Valuation: 9 Models" (main page heading
  and browser tab; changelog tab retitled to match).

## 2026-10-25 — Changelog page, batch timestamp, disclaimer

- Changelog as its own page (USMS / Portfolio Lab pattern): a Changelog link under
  the title opens a separate page rendering this file, with a back-to-dashboard
  link. The auto-generated sidebar page nav is hidden by CSS.
- Header now shows when the last batch was loaded, date and time
  ("Last batch loaded 2026-10-25 03:24 EDT"), recorded by the daily batch in the
  snapshot manifest; older snapshots without a timestamp fall back to the date.
- Red disclaimer under the title: "For educational and experimental purposes
  only. Not investment advice."

## 2026-10-25 — S&P 500 app launch

- The September 6-ticker study scaled to a live Streamlit app covering all 503
  S&P 500 constituents, refreshed by a daily batch (weekdays 18:00 ET).
- First snapshot (2026-10-25, risk-free 4.99% from ^TNX, ERP 4.5%): 503 of 503
  constituents valued. Coverage: Gordon DDM 419, two-stage DDM 420, FCFE 503,
  P/E comps 478, P/B comps 472, EV/EBITA 454, book / liquidation / replacement
  cost 503.
- Ticker lookup with a 9-model table versus price, a valuation range chart with
  a price line, sector-median anchors for the relative models, and Gordon +
  FCFE sensitivity grids computed live from stored inputs.
- Systematic assumptions (no hand peers): Gordon g 5%; dividend growth from the
  5-year dividend CAGR clipped at 18%; FCFE growth from the 5-year FCFE CAGR
  clipped at 20%; sector medians from the snapshot itself, index-wide median
  when a sector has fewer than 5 valid names.
- Data source: Yahoo Finance (yfinance). Two tickers (FDS, FERG) fall back to
  their newest fully-populated statement column (FY2025) and are flagged in the
  snapshot. MU values use FY2026 fundamentals (year ended 2026-08-31).

## 2026-09-25 — Original study: 9 models × 6 mega-caps

- Nine models across three families — present value (Gordon DDM, two-stage DDM,
  FCFE), relative multiples (P/E, P/B, EV/EBITA), asset-based (book value,
  liquidation, replacement cost) — applied to NVDA, AMD, MU, AAPL, META and
  GOOG, with the full workbook (see the repo's docs and the September
  snapshot).
- Finding that carried through to the S&P 500 app: present-value models sit
  well below market prices while relative multiples sit near or above them —
  the honest output is a wide range, not a single target price.
