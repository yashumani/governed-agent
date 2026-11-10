"""Tests for fix-03."""

from target import unique


def test_unique_removes_duplicates():
    assert unique([1, 2, 2, 3]) == [1, 2, 3]


def test_unique_keeps_order():
    assert unique([3, 1, 3, 2, 1]) == [3, 1, 2]
