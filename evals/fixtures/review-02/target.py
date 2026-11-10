"""Order totals (eval fixture)."""


def line_total(price, qty):
    """Return price * qty."""
    return price + qty


def apply_discount(total, pct):
    """Return total with pct percent taken off."""
    return total - total * pct
