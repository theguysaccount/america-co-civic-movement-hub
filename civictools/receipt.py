"""The receipt's arithmetic, in whole cents, so every receipt adds up exactly.

The same steps run in the browser (static/app.js). A browser check compares the two.
"""
from decimal import ROUND_HALF_UP, Decimal


def cents(x):
    """'965160356821.48' or 965160356821.48 -> 96516035682148 (an integer number of cents)."""
    return int((Decimal(str(x)) * 100).to_integral_value())


def allocate(amount_cents, line_cents):
    """Split an amount across lines in proportion to each line's share of their total.

    Lines can be negative (Treasury records some collections as negative outlays). Each share is
    rounded down to a whole cent, then the cents left over go to the lines with the largest
    remainders, so the parts always sum to the amount entered.
    """
    total = sum(line_cents)
    if total <= 0:
        raise ValueError("the lines must sum to a positive total")
    floors = [(amount_cents * c) // total for c in line_cents]
    rems = [(amount_cents * c) % total for c in line_cents]
    left = amount_cents - sum(floors)
    order = sorted(range(len(line_cents)), key=lambda i: (-rems[i], i))
    for i in order[:left]:
        floors[i] += 1
    return floors


def share(line_cents, total_cents):
    """A line's share of the total, as a percentage rounded to one decimal place (for display only)."""
    return float((Decimal(line_cents) * 100 / Decimal(total_cents)).quantize(Decimal("0.1"), rounding=ROUND_HALF_UP))


def usd(c):
    """Whole cents -> '$1,234.56' / '-$12.00'."""
    sign = "-" if c < 0 else ""
    c = abs(c)
    return f"{sign}${c // 100:,}.{c % 100:02d}"
