"""Unit tests for _value_matches helper."""
import asyncio
import sys
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from src.login_flow import _value_matches


def _run(coro):
    return asyncio.run(coro)


def _mock_elem(value):
    elem = MagicMock()
    elem.input_value = AsyncMock(return_value=value)
    return elem


def test_exact_match_returns_true():
    elem = _mock_elem("foo@example.com")
    assert _run(_value_matches(elem, "foo@example.com")) is True


def test_whitespace_difference_still_matches():
    elem = _mock_elem("  foo@example.com  ")
    assert _run(_value_matches(elem, "foo@example.com")) is True


def test_empty_field_does_not_match_non_empty_expected():
    elem = _mock_elem("")
    assert _run(_value_matches(elem, "foo@example.com")) is False


def test_different_value_returns_false():
    elem = _mock_elem("other@example.com")
    assert _run(_value_matches(elem, "foo@example.com")) is False


def test_input_value_exception_returns_false():
    elem = MagicMock()
    elem.input_value = AsyncMock(side_effect=RuntimeError("element detached"))
    assert _run(_value_matches(elem, "foo@example.com")) is False


def test_none_expected_matches_empty():
    elem = _mock_elem("")
    assert _run(_value_matches(elem, None)) is True
