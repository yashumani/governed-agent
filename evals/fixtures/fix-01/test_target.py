"""Tests for fix-01."""

from target import divide


def test_divide_returns_float():
    assert divide(7, 2) == 3.5


def test_divide_whole():
    assert divide(6, 3) == 2.0
