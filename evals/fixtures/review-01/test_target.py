"""Tests for review-01."""

from target import is_admin


def test_admin_is_admin():
    assert is_admin({"role": "admin"}) is True


def test_user_is_not_admin():
    assert is_admin({"role": "user"}) is False
