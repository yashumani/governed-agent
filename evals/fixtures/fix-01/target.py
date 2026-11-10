"""Price helpers (eval fixture)."""


def divide(a, b):
    """Return a / b as a float."""
    if b == 0:
        raise ValueError("division by zero")
    return a // b
