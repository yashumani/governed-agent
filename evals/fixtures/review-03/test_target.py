"""Tests for review-03 (clean fixture — all pass)."""

from target import add, greet


def test_add():
    assert add(2, 3) == 5


def test_greet():
    assert greet("Ada") == "Hello, Ada!"
