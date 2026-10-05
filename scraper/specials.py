"""Turn free-text leasing specials into terms, and compute effective (net) rent.

Specials are stored raw ({title, description}) in snapshots; build.py parses them here,
so parser improvements apply to old snapshots too.

Supported phrasing (case-insensitive), e.g.:
  "Two Months Free", "1 month free", "6 weeks free", "half a month free"
  "$500 off", "$1,000 off your first month", "$100 off per month"
  "on 12+ month leases", "12 month lease or longer", "minimum 13-month lease"
  "move in by Nov 30", "move-in by 11/30/2026", "must move in before December 1st"
  "sign by Oct 15", "lease by ...", "apply by ...", "expires 10/31", "valid through ...", "ends ..."
  "on select units/homes" -> flagged as a caveat (applicability unknown)
"""
from __future__ import annotations

import re
from dataclasses import asdict, dataclass, field
from datetime import date, datetime
from typing import List, Optional

WORD_NUMS = {
    "a": 1, "an": 1, "one": 1, "two": 2, "three": 3, "four": 4, "five": 5, "six": 6,
    "seven": 7, "eight": 8, "nine": 9, "ten": 10, "eleven": 11, "twelve": 12,
    "half a": 0.5, "half": 0.5, "1/2": 0.5, "1.5": 1.5, "one and a half": 1.5,
}
_NUM = r"(\d+(?:\.\d+)?|1/2|one and a half|half a|half|an?|one|two|three|four|five|six|seven|eight|nine|ten|eleven|twelve)"
_MONTHS = "jan|feb|mar|apr|may|jun|jul|aug|sep|sept|oct|nov|dec"
_DATE = (
    r"((?:%s)[a-z]*\.?\s+\d{1,2}(?:st|nd|rd|th)?(?:,?\s+\d{4})?|\d{4}-\d{2}-\d{2}|\d{1,2}/\d{1,2}(?:/\d{2,4})?)" % _MONTHS
)


@dataclass
class SpecialTerms:
    title: str
    description: str = ""
    months_free: float = 0.0
    one_time_off: int = 0          # dollars off once (spread over the lease)
    monthly_off: int = 0           # dollars off every month
    min_lease_months: Optional[int] = None
    move_in_by: Optional[str] = None   # ISO; unit must be available/move in on or before
    expires: Optional[str] = None      # ISO; offer must be signed by / ends on
    select_units: bool = False         # "on select units" — may not apply to every unit
    parsed: bool = False               # True if a discount amount was understood
    caveats: List[str] = field(default_factory=list)

    def to_dict(self) -> dict:
        return asdict(self)


def _num(token: str) -> float:
    token = token.lower().strip()
    return float(WORD_NUMS[token]) if token in WORD_NUMS else float(token)


def _parse_loose_date(text: str, ref: date) -> Optional[date]:
    """'Nov 30', 'November 30th, 2026', '11/30', '11/30/26' -> date; missing year = next occurrence."""
    t = re.sub(r"(\d)(st|nd|rd|th)", r"\1", text.strip().rstrip(".").replace(".", ""))
    t = re.sub(r"\s+", " ", t)
    fmts_with_year = ("%Y-%m-%d", "%b %d, %Y", "%b %d %Y", "%B %d, %Y", "%B %d %Y", "%m/%d/%Y", "%m/%d/%y")
    for fmt in fmts_with_year:
        try:
            return datetime.strptime(t, fmt).date()
        except ValueError:
            pass
    t = t.replace("Sept", "Sep").replace("sept", "sep")
    for fmt in ("%b %d", "%B %d", "%m/%d"):
        try:
            d = datetime.strptime(t, fmt).date().replace(year=ref.year)
        except ValueError:
            continue
        # A deadline with no year that's well in the past means next year (e.g. "Jan 15" seen in Dec).
        return d.replace(year=ref.year + 1) if (ref - d).days > 60 else d
    return None


def parse_special(title: str, description: str = "", ref: Optional[date] = None) -> SpecialTerms:
    ref = ref or date.today()
    terms = SpecialTerms(title=title, description=description)
    text = " ".join(f"{title}. {description}".split())
    low = text.lower()

    # --- discount amount (take the first clear statement; title usually leads) ---
    m = re.search(_NUM + r"\s+(months?|weeks?)\s+(?:of\s+)?(?:rent\s+)?free", low) or \
        re.search(r"free\s+(?:rent\s+)?(?:for\s+)?" + _NUM + r"\s+(months?|weeks?)", low)
    if m:
        qty = _num(m.group(1))
        terms.months_free = round(qty if m.group(2).startswith("month") else qty * 7 / (365 / 12), 3)
        terms.parsed = True
    elif re.search(r"\b(?:first|1st)\s+month(?:'s)?\s+(?:rent\s+)?(?:is\s+)?free\b|\bmonth\s+free\b", low):
        terms.months_free = 1.0
        terms.parsed = True

    for m in re.finditer(r"\$\s?([\d,]+)\s+off\b([^.;]*)", low):
        amount = int(m.group(1).replace(",", ""))
        tail = m.group(2)
        if re.search(r"\b(per|a|each|every)\s+month\b|/\s*mo\b|\bmonthly\b", tail):
            terms.monthly_off += amount
        else:
            terms.one_time_off += amount
        terms.parsed = True

    # --- caveats ---
    m = re.search(r"(\d{1,2})\s*\+\s*(?:-\s*)?month", low) or \
        re.search(r"(\d{1,2})[\s-]*(?:month|mo)s?[\s-]*(?:lease|term)s?\s+(?:or\s+(?:longer|more|greater)|and\s+(?:up|longer|above))", low) or \
        re.search(r"(?:minimum|min\.?|at\s+least)\s+(?:of\s+)?(?:a\s+)?(\d{1,2})[\s-]*(?:month|mo)", low) or \
        re.search(r"(?:on|with|for)\s+(?:a\s+)?(\d{1,2})[\s-]*(?:month|mo)s?[\s-]*(?:lease|term)", low)
    if m:
        terms.min_lease_months = int(m.group(1))
        terms.caveats.append(f"{terms.min_lease_months}+ month lease")

    m = re.search(r"move[\s-]*in\s+(?:on\s+or\s+)?(?:by|before|no\s+later\s+than)\s+" + _DATE, low)
    if m:
        d = _parse_loose_date(m.group(1), ref)
        if d:
            if "before" in m.group(0) and "on or before" not in m.group(0):
                d = d.fromordinal(d.toordinal() - 1)
            terms.move_in_by = d.isoformat()
            terms.caveats.append(f"move in by {d:%b %-d, %Y}")

    m = re.search(r"(?:(?:sign|lease|apply|application)\w*\s+(?:by|before)|expires?(?:\s+on)?|ends?(?:\s+on)?|"
                  r"valid\s+(?:through|thru|until|till)|through|thru|until)\s+" + _DATE, low)
    if m:
        d = _parse_loose_date(m.group(1), ref)
        if d:
            terms.expires = d.isoformat()
            terms.caveats.append(f"offer ends {d:%b %-d, %Y}")

    if re.search(r"\bselect(?:ed)?\s+(?:units?|homes?|apartments?|floor\s*plans?)\b", low):
        terms.select_units = True
        terms.caveats.append("select units only")

    return terms


@dataclass
class Effective:
    rent: int                       # effective monthly rent
    savings: int                    # listed - effective
    applied: List[str]              # titles of specials included
    skipped: List[str]              # "title: reason" for specials that don't apply
    uncertain: bool = False         # an applied special had "select units" etc.


def effective_rent(
    rent: Optional[int],
    specials: List[SpecialTerms],
    lease_months: int,
    available_date: Optional[str],
    as_of: str,
) -> Optional[Effective]:
    """Net monthly rent over the lease after applicable specials. None if nothing applies."""
    if not rent or not specials:
        return None
    total = rent * lease_months
    applied, skipped, uncertain = [], [], False
    for s in specials:
        if not s.parsed:
            skipped.append(f"{s.title}: terms not understood")
            continue
        if s.expires and s.expires < as_of:
            skipped.append(f"{s.title}: offer ended {s.expires}")
            continue
        if s.min_lease_months and lease_months < s.min_lease_months:
            skipped.append(f"{s.title}: needs a {s.min_lease_months}+ month lease (price is for {lease_months})")
            continue
        if s.move_in_by and s.move_in_by < as_of:
            skipped.append(f"{s.title}: move-in deadline {s.move_in_by} has passed")
            continue
        if s.move_in_by and available_date and available_date > s.move_in_by:
            skipped.append(f"{s.title}: unit available after the {s.move_in_by} move-in deadline")
            continue
        total -= s.months_free * rent + s.one_time_off + s.monthly_off * lease_months
        applied.append(s.title)
        uncertain = uncertain or s.select_units
    if not applied:
        return Effective(rent=rent, savings=0, applied=[], skipped=skipped) if skipped else None
    eff = round(total / lease_months)
    return Effective(rent=eff, savings=rent - eff, applied=applied, skipped=skipped, uncertain=uncertain)
