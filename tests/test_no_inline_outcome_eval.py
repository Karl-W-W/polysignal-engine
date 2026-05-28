"""
tests/test_no_inline_outcome_eval.py
====================================
Guard test for S46b: the masterloop (scanner) must NOT evaluate outcomes
in-line. Evaluation lives in exactly one place — the truth-board timer
(lab/truth_board.py, every ~15 min).

Why this guard exists
---------------------
The masterloop called lab.outcome_tracker.evaluate_outcomes in-line every
cycle from S14 through S46 (the "in-line fallback during cutover"; S42
Phase 11 was meant to retire it and never did). When S46 changed
evaluate_outcomes to score against Polymarket *resolution* instead of 4h
price drift, a scanner process still running pre-S46 code in memory kept
re-labelling migrated records with drift scoring every 5 minutes —
re-polluting the file the S46 migration had just cleaned (observed live:
213 drift-labelled records, 28 of them NEUTRAL, a status S46 never emits).

If anyone re-adds an in-line evaluate_outcomes call to the masterloop,
this test fails. The check is AST-based so the explanatory comment in
masterloop.py (which names the function) does not trip it.
"""
import ast
import inspect

from workflows import masterloop


def _call_names(tree: ast.AST):
    names = []
    for node in ast.walk(tree):
        if isinstance(node, ast.Call):
            f = node.func
            if isinstance(f, ast.Name):
                names.append((f.id, getattr(node, "lineno", "?")))
            elif isinstance(f, ast.Attribute):
                names.append((f.attr, getattr(node, "lineno", "?")))
    return names


def test_masterloop_does_not_call_evaluate_outcomes_inline():
    """No evaluate_outcomes() call anywhere in workflows/masterloop.py.

    Truth-board (lab/truth_board.py) is the SOLE evaluator post-S46b.
    """
    src = inspect.getsource(masterloop)
    tree = ast.parse(src)
    offending = [ln for (name, ln) in _call_names(tree) if name == "evaluate_outcomes"]
    assert not offending, (
        "In-line evaluate_outcomes call re-introduced in workflows/masterloop.py "
        f"at line(s) {offending}. The scanner must NOT evaluate outcomes in-line "
        "(S46b): a scanner running stale code re-pollutes the resolution-scored "
        "outcomes file with drift labels. Evaluation belongs only in "
        "lab/truth_board.py (polysignal-truth-board.timer)."
    )


def test_perception_node_specifically_is_clean():
    """Narrow check on perception_node, where the in-line call used to live."""
    src = inspect.getsource(masterloop.perception_node)
    tree = ast.parse(src)
    offending = [ln for (name, ln) in _call_names(tree) if name == "evaluate_outcomes"]
    assert not offending, (
        f"perception_node calls evaluate_outcomes at line(s) {offending} — "
        "the S46b retirement has been reverted."
    )


def test_truth_board_remains_the_evaluator():
    """Sanity: the evaluator wasn't deleted outright — truth_board still calls it.
    Guards against 'fixing' this by removing evaluation entirely."""
    from lab import truth_board
    src = inspect.getsource(truth_board)
    tree = ast.parse(src)
    names = [name for (name, _ln) in _call_names(tree)]
    assert "evaluate_outcomes" in names, (
        "truth_board.py no longer calls evaluate_outcomes — evaluation must "
        "live SOMEWHERE. S46b moves it to truth-board only, it does not delete it."
    )
