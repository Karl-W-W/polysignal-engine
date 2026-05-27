"""
tests/test_resolution_lookup.py
===============================
Unit tests for lab/_resolution_lookup.py — the gamma-API resolution checker
used by the live evaluator (lab.outcome_tracker.evaluate_outcomes) since S46.

Tests monkeypatch _http_get_json so they make no network calls.
"""

import json

import pytest

import lab._resolution_lookup as rl


def _set_responses(monkeypatch, *responses):
    """Queue gamma responses in order; one per URL tried by lookup_resolution."""
    responses = list(responses)

    def fake_get(url):
        return responses.pop(0) if responses else {"_error": "no more responses"}

    monkeypatch.setattr(rl, "_http_get_json", fake_get)


class TestStatusMapping:
    def test_closed_at_one_returns_resolved_yes(self, monkeypatch):
        _set_responses(monkeypatch, [{
            "id": "566188",
            "closed": True,
            "outcomes": '["Yes","No"]',
            "outcomePrices": '["1.0","0.0"]',
        }])
        status, info = rl.lookup_resolution("566188")
        assert status == "resolved_yes"
        assert info["closed"] is True
        assert info["outcome0_price_now"] == 1.0

    def test_closed_at_zero_returns_resolved_no(self, monkeypatch):
        _set_responses(monkeypatch, [{
            "id": "m1",
            "closed": True,
            "outcomes": '["Yes","No"]',
            "outcomePrices": '["0.0","1.0"]',
        }])
        status, info = rl.lookup_resolution("m1")
        assert status == "resolved_no"
        assert info["outcome0_price_now"] == 0.0

    def test_open_market_returns_unresolved(self, monkeypatch):
        _set_responses(monkeypatch, [{
            "id": "m1",
            "closed": False,
            "outcomes": '["Yes","No"]',
            "outcomePrices": '["0.65","0.35"]',
        }])
        status, info = rl.lookup_resolution("m1")
        assert status == "unresolved"
        assert info["closed"] is False

    def test_closed_at_mid_price_returns_ambiguous(self, monkeypatch):
        """closed=true but outcome0 in (0.01, 0.99) — refund/void/multi."""
        _set_responses(monkeypatch, [{
            "id": "m1",
            "closed": True,
            "outcomes": '["Yes","No"]',
            "outcomePrices": '["0.5","0.5"]',
        }])
        status, info = rl.lookup_resolution("m1")
        assert status == "ambiguous"

    def test_thresholds_inclusive_at_boundaries(self, monkeypatch):
        """0.99 and 0.01 themselves should resolve — not be ambiguous."""
        _set_responses(monkeypatch, [{
            "id": "m1",
            "closed": True,
            "outcomes": '["Yes","No"]',
            "outcomePrices": '["0.99","0.01"]',
        }])
        status, _ = rl.lookup_resolution("m1")
        assert status == "resolved_yes"
        _set_responses(monkeypatch, [{
            "id": "m1",
            "closed": True,
            "outcomes": '["Yes","No"]',
            "outcomePrices": '["0.01","0.99"]',
        }])
        status, _ = rl.lookup_resolution("m1")
        assert status == "resolved_no"

    def test_market_not_in_gamma_returns_not_found(self, monkeypatch):
        # All three URL attempts return an empty list (no match)
        _set_responses(monkeypatch, [], [], [])
        status, info = rl.lookup_resolution("does_not_exist")
        assert status == "not_found"
        assert info == {}


class TestFallbackUrls:
    def test_falls_back_to_second_url_on_first_error(self, monkeypatch):
        _set_responses(
            monkeypatch,
            {"_error": "timeout"},  # /markets?id=...
            [{                       # /markets?clob_token_ids=...
                "id": "m1",
                "closed": True,
                "outcomes": '["Yes","No"]',
                "outcomePrices": '["1.0","0.0"]',
            }],
        )
        status, _ = rl.lookup_resolution("m1")
        assert status == "resolved_yes"

    def test_falls_back_to_third_url_on_first_two_misses(self, monkeypatch):
        _set_responses(
            monkeypatch,
            [],                                 # /markets?id=...  (no match)
            {"_error": "500"},                  # /markets?clob_token_ids=...
            {                                   # /markets/{mid}
                "id": "m1",
                "closed": True,
                "outcomes": '["Yes","No"]',
                "outcomePrices": '["0.0","1.0"]',
            },
        )
        status, _ = rl.lookup_resolution("m1")
        assert status == "resolved_no"


class TestParsing:
    def test_parses_list_format_outcomes_and_prices(self, monkeypatch):
        """gamma sometimes returns native lists instead of JSON strings."""
        _set_responses(monkeypatch, [{
            "id": "m1",
            "closed": True,
            "outcomes": ["Yes", "No"],
            "outcomePrices": ["1.0", "0.0"],
        }])
        status, info = rl.lookup_resolution("m1")
        assert status == "resolved_yes"
        assert info["outcomes"] == ["Yes", "No"]

    def test_matches_by_clob_token_ids_when_id_does_not_match(self, monkeypatch):
        _set_responses(monkeypatch, [{
            "id": "different_id",
            "clobTokenIds": '["m1","m1-no"]',
            "closed": True,
            "outcomes": '["Yes","No"]',
            "outcomePrices": '["1.0","0.0"]',
        }])
        status, _ = rl.lookup_resolution("m1")
        assert status == "resolved_yes"
