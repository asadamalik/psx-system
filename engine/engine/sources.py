"""
sources.py
----------
Investing.com URL map. Each PSX symbol maps to an Investing.com slug; each
data section maps to a URL suffix.

Fetching is performed by Claude (Cowork web fetch) — these URLs tell Claude
what to fetch. The headless fetch returns the ANNUAL view of statement pages
(the Quarterly tab is JavaScript-only), which is what scoring uses.
"""

BASE = "https://www.investing.com/equities/"

# section -> URL suffix
SECTION_SUFFIX = {
    "overview": "",
    "financial_summary": "-financial-summary",
    "income_statement": "-income-statement",
    "balance_sheet": "-balance-sheet",
    "cash_flow": "-cash-flow",
    "ratios": "-ratios",
    "dividends": "-dividends",
    "earnings": "-earnings",
    "forecast": "-forecast",
    "historical": "-historical-data",
    "technical": "-technical",
    "profile": "-company-profile",
}

# The sections worth auto-fetching for the fundamental pipeline
FUNDAMENTAL_SECTIONS = ["income_statement", "balance_sheet", "cash_flow",
                        "ratios", "earnings", "dividends", "overview"]

# PSX symbol -> Investing.com slug. Extend as you add stocks.
SLUGS = {
    "MLCF": "maple-leaf-cement-factory-ltd",
    "FFC": "fauji-fertiliz",
    "SYS": "systems-ltd",
    "KEL": "k-electric",
    "PIBTL": "pakistan-intl-bulk-terminal-private",
    "PAEL": "pak-electron",
    "WTL": "wrldcal-teleco",
    "CNERGY": "byco-petroleum",
    "BOP": "bank-of-punjab",
}


def urls_for(slug: str) -> dict:
    """All section URLs for an Investing.com slug."""
    return {sec: f"{BASE}{slug}{suf}" for sec, suf in SECTION_SUFFIX.items()}


def url(slug: str, section: str) -> str:
    return f"{BASE}{slug}{SECTION_SUFFIX[section]}"
