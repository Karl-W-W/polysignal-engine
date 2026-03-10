#!/usr/bin/env python3
"""
tests/test_moltbook_math_solver.py
====================================
Tests for lab/moltbook_math_solver.py — MoltBook math verification solver.
"""

import os
import sys
from unittest.mock import patch, MagicMock

import pytest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from lab.moltbook_math_solver import (
    parse_math_challenge,
    solve_expression,
    solve_verification_challenge,
    ensure_verified,
)


# ============================================================================
# EXPRESSION PARSING
# ============================================================================

class TestParseMathChallenge:
    def test_direct_expression(self):
        expr = parse_math_challenge("Solve: 42.5 + 17.3")
        assert expr is not None
        assert "42.5" in expr
        assert "17.3" in expr

    def test_calculate_keyword(self):
        expr = parse_math_challenge("Calculate: (25 + 15) * 2")
        assert expr is not None

    def test_what_is_keyword(self):
        expr = parse_math_challenge("What is 100 / 3?")
        assert expr is not None
        assert "100" in expr

    def test_compute_keyword(self):
        expr = parse_math_challenge("Compute: 3.14 * 2.0 - 1.28")
        assert expr is not None

    def test_word_numbers(self):
        expr = parse_math_challenge("What is twenty plus thirty?")
        assert expr is not None

    def test_bare_expression(self):
        expr = parse_math_challenge("Please answer: 7 * 8 + 3")
        assert expr is not None

    def test_no_expression(self):
        expr = parse_math_challenge("Hello world, how are you?")
        assert expr is None

    def test_word_operators(self):
        expr = parse_math_challenge("What is ten times five?")
        assert expr is not None


# ============================================================================
# EXPRESSION SOLVING
# ============================================================================

class TestSolveExpression:
    def test_basic_addition(self):
        assert solve_expression("42.5 + 17.3") == 59.8

    def test_basic_multiplication(self):
        assert solve_expression("7 * 8") == 56.0

    def test_division(self):
        assert solve_expression("100 / 3") == 33.33

    def test_complex_expression(self):
        assert solve_expression("(25 + 15) * 2") == 80.0

    def test_decimal_precision(self):
        assert solve_expression("3.14 * 2.0 - 1.28") == 5.0

    def test_rejects_unsafe_input(self):
        assert solve_expression("import os; os.system('rm -rf /')") is None

    def test_rejects_letters(self):
        assert solve_expression("abc + 123") is None

    def test_empty_string(self):
        assert solve_expression("") is None

    def test_parentheses(self):
        assert solve_expression("(10 + 5) * (3 - 1)") == 30.0

    def test_negative_result(self):
        assert solve_expression("5 - 10") == -5.0


# ============================================================================
# VERIFICATION FLOW
# ============================================================================

class TestVerificationChallenge:
    @patch("lab.moltbook_math_solver.requests.get")
    def test_already_verified(self, mock_get):
        mock_resp = MagicMock()
        mock_resp.status_code = 200
        mock_resp.json.return_value = {"verified": True}
        mock_get.return_value = mock_resp

        success, msg = solve_verification_challenge("test_jwt")
        assert success is True
        assert "Already verified" in msg

    @patch("lab.moltbook_math_solver.requests.post")
    def test_solve_challenge(self, mock_post):
        mock_resp = MagicMock()
        mock_resp.status_code = 200
        mock_resp.json.return_value = {"success": True, "verified": True}
        mock_resp.raise_for_status = MagicMock()
        mock_post.return_value = mock_resp

        challenge = {"challenge": "Solve: 10 + 20"}
        success, msg = solve_verification_challenge("test_jwt", challenge_data=challenge)
        assert success is True
        assert "30.00" in msg

    def test_unparseable_challenge(self):
        challenge = {"challenge": "No math here at all"}
        success, msg = solve_verification_challenge("test_jwt", challenge_data=challenge)
        assert success is False
        assert "Could not parse" in msg

    @patch("lab.moltbook_math_solver.requests.post")
    @patch("lab.moltbook_math_solver.requests.get")
    def test_ensure_verified_success(self, mock_get, mock_post):
        mock_get_resp = MagicMock()
        mock_get_resp.status_code = 200
        mock_get_resp.json.return_value = {"verified": True}
        mock_get.return_value = mock_get_resp

        assert ensure_verified("test_jwt", max_attempts=1) is True

    @patch("lab.moltbook_math_solver.requests.get")
    def test_ensure_verified_failure(self, mock_get):
        mock_resp = MagicMock()
        mock_resp.status_code = 403
        mock_resp.json.return_value = {"challenge": "No math here at all"}
        mock_get.return_value = mock_resp

        assert ensure_verified("test_jwt", max_attempts=1) is False
