# ABOUTME: Tests the tally of Tom's ratings and the figures of each model.
# ABOUTME: Checks the counts, the figures and that nothing is shown before all is rated.

import pytest

from answer_models import write_json
from tally_ratings import get_tally, get_tally_text

QUESTIONS = [{"question_id": "Q01"}, {"question_id": "Q03"}, {"question_id": "Q04"}]
KEY = {"Q01": {"A": "gpt-6-luna", "B": "gpt-4o-mini"},
       "Q03": {"A": "gpt-4o-mini", "B": "gpt-6-luna"},
       "Q04": {"A": "gpt-4o-mini", "B": "gpt-6-luna"}}
# the rating and factual error of each position
RATINGS = {"Q01": {"A": ("perfect", False), "B": ("not_good", True)},
           "Q03": {"A": ("ok", False), "B": ("perfect", False)},
           "Q04": {"A": ("perfect", False), "B": ("ok", True)}}
# latency, reasoning tokens and cost of each model's answers
FIGURES = {"gpt-4o-mini": [(4.0, 0, .001), (6.0, 0, .002), (9.0, 0, .003)],
           "gpt-6-luna": [(10.0, 50, .002), (30.0, 70, .004), (20.0, 400, .009)]}


def save_ratings(pathOutput, dctRatings):
    write_json(str(pathOutput / "ratings.json"), {
        strId: {strPosition: {"rating": strRating, "factual_error": bError, "note": ""}
                for strPosition, (strRating, bError) in dctPositions.items()}
        for strId, dctPositions in dctRatings.items()})


@pytest.fixture
def output(tmp_path):
    write_json(str(tmp_path / "key.json"), KEY)
    save_ratings(tmp_path, RATINGS)
    for strModel, lstFigures in FIGURES.items():
        for dctQuestion, (fLatency, intReasoning, fCost) in zip(QUESTIONS, lstFigures):
            strId = dctQuestion["question_id"]
            write_json(str(tmp_path / "answers" / f"{strId}_{strModel}.json"),
                       {"question_id": strId, "model": strModel, "answer": "x",
                        "latency": fLatency, "reasoning_tokens": intReasoning, "cost": fCost})
    return tmp_path


def test_ratings_and_figures_are_counted_per_model(output):
    assert get_tally(str(output), QUESTIONS) == {
        "gpt-4o-mini": {"perfect": 1, "ok": 1, "not_good": 1, "factual_errors": 1, "failed": 0,
                        "median_latency": 6.0, "median_reasoning_tokens": 0,
                        "cost_per_answer": pytest.approx(.002)},
        "gpt-6-luna": {"perfect": 2, "ok": 1, "not_good": 0, "factual_errors": 1, "failed": 0,
                       "median_latency": 20.0, "median_reasoning_tokens": 70,
                       "cost_per_answer": pytest.approx(.005)}}


def test_only_the_given_questions_are_counted(output):
    dctTally = get_tally(str(output), QUESTIONS[:1])
    assert dctTally["gpt-6-luna"]["perfect"] == 1
    assert dctTally["gpt-6-luna"]["ok"] == 0
    assert dctTally["gpt-4o-mini"]["median_latency"] == 4.0


def test_a_failed_answer_is_counted_as_failed_only(output):
    write_json(str(output / "answers" / "Q04_gpt-6-luna.json"),
               {"question_id": "Q04", "model": "gpt-6-luna", "latency": 600.0, "error": "broken"})
    write_json(str(output / "key.json"), KEY | {"Q04": {"A": "gpt-4o-mini"}})
    dctLuna = get_tally(str(output), QUESTIONS)["gpt-6-luna"]
    assert dctLuna["failed"] == 1
    assert dctLuna["ok"] == 0
    assert dctLuna["median_latency"] == 20.0


@pytest.mark.parametrize("dctChange", [
    {"Q03": {"A": ("ok", False)}}, {"Q03": {"A": ("ok", False), "B": (None, True)}}])
def test_nothing_is_shown_before_all_is_rated(output, dctChange):
    save_ratings(output, RATINGS | dctChange)
    with pytest.raises(ValueError, match="Not rated yet: Q03-B"):
        get_tally(str(output), QUESTIONS)


def test_a_question_that_has_not_been_reviewed_is_not_rated(output):
    with pytest.raises(ValueError, match="Not rated yet: Q99"):
        get_tally(str(output), QUESTIONS + [{"question_id": "Q99"}])


def test_the_text_has_a_row_for_each_model(output):
    lstLines = get_tally_text(get_tally(str(output), QUESTIONS)).splitlines()
    assert lstLines[0].split() == ["model", "perfect", "ok", "not_good", "errors", "failed",
                                   "median_s", "reasoning", "$/answer"]
    assert lstLines[1].split() == ["gpt-4o-mini", "1", "1", "1", "1", "0", "6.0", "0", "0.00200"]
    assert lstLines[2].split() == ["gpt-6-luna", "2", "1", "0", "1", "0", "20.0", "70", "0.00500"]
