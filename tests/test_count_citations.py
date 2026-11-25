# ABOUTME: Tests the count of the citations in the answers of the trial of numbered chunks.
# ABOUTME: The answers are written for the tests: valid, a number too high, none, other forms.

import json

import pytest

from count_citations import count_answer, find_numbers, find_other_forms, has_source_list, \
    median_figures, read_answers, report

IDS = ["a0", "a1", "b0", "c0"]


def answer(strText, strId="Q01", lstIds=IDS):
    return {"question_id": strId, "ids": lstIds, "numbered_docs": True, "answer": strText,
            "prompt_tokens": 4000, "completion_tokens": 300, "reasoning_tokens": 200,
            "latency": 3.0, "cost": .0006}


def test_numbers_of_the_form_asked_are_found_in_order():
    assert find_numbers("Torque it to 40 ft-lb [3]. Use AN bolts [1][4].") == [3, 1, 4]


def test_numbers_written_with_a_comma_are_found():
    assert find_numbers("Both say so [2, 4].") == [2, 4]


def test_figures_in_parentheses_and_brackets_of_links_are_not_numbers():
    assert find_numbers("It is 16 ft 11 in (5.15 m) long; see [AC 43.13](https://x).") == []


@pytest.mark.parametrize("strText, lstExpected", [
    ("Use flox (3).", ["(3)"]),
    ("Use flox (2, 3).", ["(2, 3)"]),
    ("Use flox [source 3].", ["[source 3]"]),
    ("Use flox (see piece 3).", ["(see piece 3)"]),
    ("Use flox [3: chapter 4].", ["[3: chapter 4]"]),
    ("Use flox [3][4] and [2, 4].", []),
    ("It is 16 ft 11 in (5.15 m) long.", []),
    ("See [AC 43.13-1B](https://example.com/ac4313).", []),
])
def test_citations_in_another_form_are_found(strText, lstExpected):
    assert find_other_forms(strText) == lstExpected


@pytest.mark.parametrize("strText, bExpected", [
    ("Use flox [1].\n\nSources:\n- [1] thread", True),
    ("Use flox [1].\n\n**References**\n[1] news 78", True),
    ("Use flox [1].\n\n### Sources\n1. thread", True),
    ("Use flox [1]. The sources agree on this.", False),
])
def test_a_list_of_sources_is_found(strText, bExpected):
    assert has_source_list(strText) is bExpected


def test_a_valid_answer_is_counted():
    dctCount = count_answer(answer("Torque [3]. Bolts [1][3]. Primer [2, 4]."))
    assert dctCount == {"question_id": "Q01", "numbers": 5, "distinct": 4, "sent": 4,
                        "no_chunk": [], "other_forms": [], "source_list": False}


def test_a_number_too_high_names_no_chunk():
    assert count_answer(answer("Torque [3]. Bolts [5][0]."))["no_chunk"] == [5, 0]


def test_the_report_lists_each_fault(tmp_path):
    lstAnswers = [answer("Torque [3].", "Q01"),
                  answer("Torque is 40 ft-lb.", "Q02"),
                  answer("Torque [9].", "Q03"),
                  answer("Torque (3).", "Q04"),
                  answer("Torque [1].\n\nSources:\n[1] a thread", "Q05")]
    strReport = report(lstAnswers, {})
    assert "Answers without a number (2): Q02, Q04" in strReport
    assert "Numbers that name no chunk (1): Q03 [9]" in strReport
    assert "Citations in another form (1): Q04 (3)" in strReport
    assert "Lists of sources (1): Q05" in strReport
    assert "| Q01 | 1 | 1 | 4 |" in strReport


def test_the_report_puts_the_medians_beside_those_of_the_rated_answers():
    lstAnswers = [answer("[1]", "Q01"), answer("[1]", "Q02") | {"latency": 5.0}]
    dctRated = {"Q01": answer("", "Q01") | {"latency": 1.0}, "Q02": answer("", "Q02")}
    strReport = report(lstAnswers, dctRated)
    assert "| latency | 4.00 | 2.00 |" in strReport


def test_medians_are_taken_over_the_figures_of_each_answer():
    dctMedians = median_figures([{"latency": 1.0, "cost": .1}, {"latency": 3.0, "cost": .2},
                                 {"latency": 2.0, "cost": .4}])
    assert dctMedians["latency"] == 2.0
    assert dctMedians["cost"] == .2


def test_answers_and_their_rated_answers_are_read(tmp_path):
    (tmp_path / "trial").mkdir()
    (tmp_path / "rated").mkdir()
    (tmp_path / "trial" / "Q02_gpt-6-luna.json").write_text(json.dumps(answer("[1]", "Q02")))
    (tmp_path / "trial" / "Q01_gpt-6-luna.json").write_text(json.dumps(answer("[1]", "Q01")))
    (tmp_path / "rated" / "Q01_gpt-6-luna.json").write_text(json.dumps(answer("x", "Q01")))
    (tmp_path / "rated" / "Q01_gpt-4o-mini.json").write_text(json.dumps(answer("y", "Q01")))
    lstAnswers, dctRated = read_answers(tmp_path / "trial", tmp_path / "rated")
    assert [d["question_id"] for d in lstAnswers] == ["Q01", "Q02"]
    assert list(dctRated) == ["Q01"]
    assert dctRated["Q01"]["answer"] == "x"
