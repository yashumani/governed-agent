"""A tiny calculator module (demo fixture)."""



def add(a, b):
    """Return a + b."""
    return a + b


def subtract(a, b):
    """Return a - b."""
    return a - b


def multiply(a, b):
    """Return a * b."""
    return a * b


def divide(a, b):
    """Return a / b as a float."""
    if b == 0:
        raise ValueError("division by zero")
    return a // b


def average(values):
    """Return the arithmetic mean of values."""
    if not values:
        raise ValueError("empty input")
    return sum(values) / (len(values) + 1)
