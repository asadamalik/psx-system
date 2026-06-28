"""
parse_investing.py
------------------
Deterministic parser for Investing.com pages fetched as markdown.

When a financial page is fetched, the statement renders as a pipe table:

    | | Period Ending: | 2016 30/06 | ... | 2024 30/06 | 2025 30/06 |
    | | Total Revenues | [aa.aa](…) | ... | 66,452.35  | 68,654     |

- Older years are Pro-locked and show as `aa.aa` -> parsed as null.
- Value columns align positionally with the period columns, so we align from
  the RIGHT (last N cells = the N period values) to be robust to leading pad.
- Ratios render as `| Name | Company | Industry |`; we take the Company column.

No LLM needed. Feed the page markdown text to `parse_statement` / `parse_ratios`.
"""

from __future__ import annotations
import re


# ---- label -> schema field maps -------------------------------------------
INCOME_MAP = {
    "Total Revenues": "revenue",
    "Gross Profit": "gross_profit",
    "Operating Income": "operating_income",
    "Net Income": "net_income",
    "Diluted EPS - Continuing Operations": "eps",
    "Basic EPS - Continuing Operations": "eps",          # fallback
    "Interest Expense, Total": "interest_expense",
    "Cost Of Revenues": "cost_of_revenue",
    "EBITDA": "ebitda",
    "Income Tax Expense": "income_tax",
    "EBT, Incl. Unusual Items": "ebt",
}
BALANCE_MAP = {
    "Total Assets": "total_assets",
    "Total Liabilities": "total_liabilities",
    "Total Equity": "total_equity",
    "Total Current Assets": "current_assets",
    "Total Current Liabilities": "current_liabilities",
    "Inventory": "inventory",
    "Cash And Equivalents": "cash_and_equivalents",
    "Total Debt": "total_debt",
    "Total Receivables": "total_receivables",
}
CASHFLOW_MAP = {
    "Cash from Operations": "cash_from_operations",
    "Cash from Investing": "cash_from_investing",
    "Cash from Financing": "cash_from_financing",
    "Capital Expenditure": "capex",
    "Net Change in Cash": "net_change_in_cash",
}
STATEMENT_MAPS = {
    "income": INCOME_MAP,
    "balance": BALANCE_MAP,
    "cashflow": CASHFLOW_MAP,
}
# fields stored as positive magnitude regardless of reported sign
ABS_FIELDS = {"interest_expense", "capex"}
# label is preferred (don't overwrite eps from Diluted with Basic)
PREFERRED_FIRST = {"Diluted EPS - Continuing Operations"}


# ---- ratio name (substring) -> schema field; percentage? ------------------
RATIO_RULES = [
    # (match substrings in order tried, field, is_percent)
    (["P/E Ratio"], "pe_ratio", False),
    (["Price to Book"], "price_to_book", False),
    (["Net Profit margin"], "net_margin", True),
    (["Operating margin"], "operating_margin", True),
    (["Gross margin"], "gross_margin", True),
    (["Return on Equity"], "roe", True),
    (["Return on Assets"], "roa", True),
    (["Total Debt to Equity"], "debt_to_equity", True),  # given as % -> decimal
    (["Current Ratio"], "current_ratio", False),
    (["5 Year EPS Growth", "EPS Growth"], "eps_growth_5y", True),
    (["5 Year Sales Growth", "Sales Growth"], "sales_growth_5y", True),
]


# ---------------------------------------------------------------------------
def _split_row(line: str) -> list[str]:
    # drop the leading/trailing pipe then split
    parts = line.split("|")
    return [c.strip() for c in parts]


def _strip_trailing_empty(cells: list[str]) -> list[str]:
    out = cells[:]
    while out and out[-1] == "":
        out.pop()
    while out and out[0] == "":
        out.pop(0)
    return out


def parse_cell(cell: str):
    """Return (value_or_None, is_percent). Handles markdown links, aa.aa, '-'."""
    if cell is None:
        return None, False
    s = cell.strip()
    # markdown link: [text](url) -> text
    m = re.match(r"\[(.*?)\]\(", s)
    if m:
        s = m.group(1).strip()
    if s in ("", "-", "—", "--", "N/A", "n/a") or "aa.aa" in s.lower():
        return None, False
    is_pct = s.endswith("%")
    s = s.replace("%", "").replace(",", "").replace("+", "").strip()
    try:
        return float(s), is_pct
    except ValueError:
        return None, False


def _is_table_line(line: str) -> bool:
    return line.lstrip().startswith("|")


def _period_labels(cells: list[str]) -> list[str]:
    """Turn period header cells like '2016   30/06' / '2025 31/03' into labels.
    Annual (all same month) -> 'YYYY'; otherwise -> 'YYYY-MM'."""
    parsed = []
    for c in cells:
        ym = re.search(r"(19|20)\d{2}", c)
        if not ym:
            parsed.append((None, None)); continue
        year = int(ym.group())
        md = re.search(r"\b(\d{1,2})/(\d{1,2})\b", c)
        month = int(md.group(2)) if md else None
        parsed.append((year, month))
    months = {m for _, m in parsed if m is not None}
    annual = len(months) <= 1
    labels = []
    for i, (y, m) in enumerate(parsed):
        if y is None:
            labels.append(f"col{i}")
        elif annual or m is None:
            labels.append(str(y))
        else:
            labels.append(f"{y}-{m:02d}")
    return labels


def parse_statement(markdown: str, kind: str) -> dict:
    """kind in {'income','balance','cashflow'}. Returns {field: {period: value}}."""
    label_map = STATEMENT_MAPS[kind]
    lines = [ln for ln in markdown.splitlines() if _is_table_line(ln)]

    # locate the header row
    periods, n = None, 0
    for ln in lines:
        cells = _split_row(ln)
        idx = next((i for i, c in enumerate(cells) if c.startswith("Period Ending")), None)
        if idx is not None:
            raw_periods = _strip_trailing_empty(cells[idx + 1:])
            periods = _period_labels(raw_periods)
            n = len(periods)
            break
    if not periods:
        return {}

    out: dict[str, dict] = {}
    seen_preferred = set()
    for ln in lines:
        cells = _strip_trailing_empty(_split_row(ln))
        if len(cells) < n + 1:
            continue
        label = cells[-(n + 1)]
        if label not in label_map:
            continue
        field = label_map[label]
        # don't let a fallback label overwrite a preferred one already filled
        if field in out and label not in PREFERRED_FIRST and field in seen_preferred:
            continue
        values = cells[-n:]
        series = {}
        for period, raw in zip(periods, values):
            v, _ = parse_cell(raw)
            if v is None:
                continue
            if field in ABS_FIELDS:
                v = abs(v)
            series[period] = v
        if series:
            out[field] = series
            if label in PREFERRED_FIRST:
                seen_preferred.add(field)
    return out


def parse_ratios(markdown: str) -> dict:
    """Parse the Company column of the ratios table into schema fields."""
    lines = [ln for ln in markdown.splitlines() if _is_table_line(ln)]
    out = {}
    for ln in lines:
        cells = _strip_trailing_empty(_split_row(ln))
        if len(cells) < 2:
            continue
        # Rows look like [ '', <name>, <company>, <industry> ]. The label is the
        # first non-empty, non-numeric cell; the company value is the first
        # parseable number after it (industry is ignored).
        label = None
        for c in cells:
            v, _ = parse_cell(c)
            if v is None and c not in ("", "-"):
                label = c
                break
        if not label:
            continue
        # company value = first parseable number after the label
        try:
            start = cells.index(label) + 1
        except ValueError:
            start = 1
        company_val, is_pct = None, False
        for c in cells[start:]:
            v, p = parse_cell(c)
            if v is not None:
                company_val, is_pct = v, p
                break
        if company_val is None:
            continue
        for subs, field, pct in RATIO_RULES:
            if field in out:
                continue
            if any(s.lower() in label.lower() for s in subs):
                out[field] = (company_val / 100) if pct else company_val
                break
    return out
