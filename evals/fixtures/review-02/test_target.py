"""Tests for review-02."""

from target import apply_discount, line_total


def test_line_total():
    assert line_total(10, 3) == 30


def test_apply_discount():
    assert apply_discount(100, 20) == 80
