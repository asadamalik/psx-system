"""
config.py
---------
Central, tweakable configuration: scoring weights, rating bands, and the
thresholds used to grade each fundamental/technical metric.

Everything that encodes "investment opinion" lives here so the rest of the
engine stays mechanical. Edit these to match your own strategy.
"""

# ---------------------------------------------------------------------------
# Final score weighting
# ---------------------------------------------------------------------------
FUNDAMENTAL_WEIGHT = 0.70
TECHNICAL_WEIGHT = 0.30

# ---------------------------------------------------------------------------
# Fundamental sub-pillar weights (must sum to 1.0)
# ---------------------------------------------------------------------------
FUNDAMENTAL_PILLARS = {
    "growth": 0.30,
    "profitability": 0.30,
    "financial_strength": 0.25,
    "valuation": 0.15,
}

# ---------------------------------------------------------------------------
# Rating bands (applied to overall_score 0-100)
# ---------------------------------------------------------------------------
RATING_BANDS = [
    (80, "Strong Buy"),
    (65, "Buy"),
    (50, "Hold"),
    (35, "Reduce"),
    (0,  "Sell"),
]

# ---------------------------------------------------------------------------
# Metric thresholds: (t1, t2, t3) ascending boundaries -> 0/33/66/100 sub-score
# higher_better=False inverts (lower value scores higher, e.g. debt, P/E).
# Values are PSX-reasonable defaults; tune freely.
# ---------------------------------------------------------------------------
FUND_THRESHOLDS = {
    # growth (decimals, e.g. 0.15 = 15%)
    "revenue_growth_5y":    {"t": (0.0, 0.08, 0.18), "higher_better": True},
    "net_income_growth_5y": {"t": (0.0, 0.08, 0.18), "higher_better": True},
    "eps_growth":           {"t": (0.0, 0.08, 0.18), "higher_better": True},
    "sales_growth":         {"t": (0.0, 0.08, 0.18), "higher_better": True},
    # profitability
    "roe":                  {"t": (0.0, 0.10, 0.20), "higher_better": True},
    "roa":                  {"t": (0.0, 0.05, 0.10), "higher_better": True},
    "gross_margin":         {"t": (0.10, 0.25, 0.40), "higher_better": True},
    "operating_margin":     {"t": (0.05, 0.12, 0.20), "higher_better": True},
    "net_margin":           {"t": (0.0, 0.08, 0.15), "higher_better": True},
    # financial strength
    "debt_to_equity":       {"t": (0.5, 1.0, 2.0), "higher_better": False},
    "current_ratio":        {"t": (1.0, 1.5, 2.0), "higher_better": True},
    "interest_coverage":    {"t": (1.5, 4.0, 8.0), "higher_better": True},
    "fcf_margin":           {"t": (0.0, 0.05, 0.12), "higher_better": True},
    # valuation
    "pe_ratio":             {"t": (10, 18, 30), "higher_better": False},
    "price_to_book":        {"t": (1.0, 2.5, 5.0), "higher_better": False},
    "peg":                  {"t": (1.0, 2.0, 3.0), "higher_better": False},
}

# Which metrics feed each fundamental pillar
PILLAR_METRICS = {
    "growth": ["revenue_growth_5y", "net_income_growth_5y", "eps_growth", "sales_growth"],
    "profitability": ["roe", "roa", "gross_margin", "operating_margin", "net_margin"],
    "financial_strength": ["debt_to_equity", "current_ratio", "interest_coverage", "fcf_margin"],
    "valuation": ["pe_ratio", "price_to_book", "peg"],
}

# ---------------------------------------------------------------------------
# Risk model: derived from leverage + volatility + valuation stretch
# ---------------------------------------------------------------------------
RISK_BANDS = [
    (66, "Low"),
    (40, "Medium"),
    (0,  "High"),
]

# Sections expected in raw/ (drives the "what still needs extraction" report)
RAW_SECTIONS = [
    "income_statement_annual", "income_statement_quarterly",
    "balance_sheet_annual", "balance_sheet_quarterly",
    "cashflow_annual", "cashflow_quarterly",
    "ratio", "earnings", "dividends",
    "overview", "profile", "ownership", "news",
]
