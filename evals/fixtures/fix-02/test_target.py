"""Tests for fix-02."""

from target import slugify


def test_slugify_replaces_spaces():
    assert slugify("Hello World") == "hello-world"


def test_slugify_lowercases():
    assert slugify("ABC") == "abc"
