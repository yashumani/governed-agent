"""Tests for the calculator demo fixture."""

from calculator import add, average, divide, multiply, subtract


def test_add():
    assert add(2, 3) == 5


def test_subtract():
    assert subtract(5, 3) == 2


def test_multiply():
    assert multiply(3, 4) == 12


def test_divide_returns_float():
    assert divide(7, 2) == 3.5


def test_average():
    assert average([2, 4, 6]) == 4.0
