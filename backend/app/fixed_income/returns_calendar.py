"""Versioned national financial calendar, reviewed against ANBIMA 2024/2025/2026.

Not a universal CDB convention: the caller must explicitly select this calendar.
No extrapolation beyond the reviewed years; no remote holiday dependency.
"""
from datetime import date, timedelta

CALENDAR = "anbima_2024_2026_v1"
HOLIDAYS = {
    2024: "01-01 02-12 02-13 03-29 04-21 05-01 05-30 09-07 10-12 11-02 11-15 11-20 12-25",
    2025: "01-01 03-03 03-04 04-18 04-21 05-01 06-19 09-07 10-12 11-02 11-15 11-20 12-25",
    2026: "01-01 02-16 02-17 04-03 04-21 05-01 06-04 09-07 10-12 11-02 11-15 11-20 12-25",
}
HOLIDAYS = {year: frozenset(date.fromisoformat(f"{year}-{day}") for day in days.split()) for year, days in HOLIDAYS.items()}


def business_dates(start: date, end: date):
    """Start inclusive, end exclusive. None means calendar coverage unavailable."""
    if start > end:
        raise ValueError("Inverted accrual dates")
    if any(year not in HOLIDAYS for year in range(start.year, end.year + 1)):
        return None
    return tuple(day for offset in range((end - start).days)
        if (day := start + timedelta(days=offset)).weekday() < 5 and day not in HOLIDAYS[day.year])
