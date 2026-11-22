# ABOUTME: Tests how an answer is shown: tables, lists and text that tries to act as HTML.
# ABOUTME: The answers are real ones; the pages are read through Flask's test client.

import json
import os
import re

import pytest

from answer_models import write_json
from review_answers import create_app
from src.answer_html import get_answer_html

ANSWERS = os.path.join(os.path.dirname(__file__), "answers")
HOSTILE = """Look <script>alert(1)</script> and <img src=x onerror=alert(1)>

<script>alert(2)</script>

![picture](https://example.com/p.png) and [a](javascript:alert(1)) and [b](JaVaScRiPt:alert(1))
and [c](data:text/html,x) and [d](vbscript:x) and [e](file:///etc/passwd) and <javascript:alert(1)>
and [f]

[f]: javascript:alert(1)

<iframe src="https://example.com"></iframe>
"""


def read_answer(strName):
    with open(os.path.join(ANSWERS, strName + ".md")) as f:
        return f.read()


@pytest.fixture
def show(client, jobs_dir):
    """Gives the results page of a job with the given answer."""
    def get_page(strAnswer):
        dctJob = {"process_id": "done", "status": "complete", "created": 1.0, "elapsed": 2.5,
                  "type": "new", "query": "q",
                  "result": {"answer": strAnswer, "provided_docs": [], "related_docs": []}}
        (jobs_dir / "done.json").write_text(json.dumps(dctJob))
        response = client.get("/cozyrag/done/processid")
        assert response.status_code == 200
        return response.get_data(as_text=True)
    return get_page


# ---- the function
def test_a_table_is_shown_as_a_table():
    strHtml = get_answer_html(read_answer("answer_with_table"))
    assert "<table>" in strHtml
    assert "<td>" in strHtml
    assert not re.search(r"^\|", strHtml, re.M)


def test_the_alignment_of_a_column_is_kept():
    strHtml = get_answer_html("| a | b |\n|---|--:|\n| 1 | 2 |\n")
    assert '<td style="text-align:right">2</td>' in strHtml


def test_a_list_directly_after_a_text_line_is_a_list():
    strHtml = get_answer_html("Check:\n- one\n- two\n")
    assert strHtml.count("<li>") == 2


def test_bullets_indented_under_a_numbered_item_are_a_list_inside_it():
    strHtml = get_answer_html(read_answer("answer_with_nested_bullets"))
    assert re.search(r"<li>(?:(?!</li>).)*<ul>\s*<li>Measure the distance", strHtml, re.S)


def test_a_picture_is_not_shown():
    strHtml = get_answer_html("![p](https://example.com/p.png)")
    assert "<img" not in strHtml
    assert 'href="https://example.com/p.png"' in strHtml


@pytest.mark.parametrize("strText", [HOSTILE, "<b onclick=x>hi</b>", '[x](https://e.com "a\\" onclick=b")'])
def test_no_tag_or_attribute_of_the_answer_reaches_the_page_as_html(strText):
    strHtml = get_answer_html(strText)
    # what is written by the renderer itself
    lstTags = re.findall(r"<(?!/)([a-z0-9]+)([^>]*)>", strHtml)
    assert {strTag for strTag, _ in lstTags} <= {"p", "a", "ul", "li", "strong", "em"}
    for strTag, strAttributes in lstTags:
        assert " on" not in re.sub(r'"[^"]*"', '""', strAttributes)
    assert not re.search(r'href="(javascript|data|vbscript|file):', strHtml, re.I)


# ---- the results page
def test_the_results_page_shows_a_table(show):
    strPage = show(read_answer("answer_with_table"))
    assert "<table>" in strPage
    assert not re.search(r"^\s*\|", strPage, re.M)


def test_the_results_page_shows_a_list_after_a_text_line(show):
    assert show(read_answer("answer_with_list_after_text")).count("<li>") >= 3


def test_the_results_page_shows_hostile_text_as_text(show):
    strPage = show(HOSTILE)
    assert "<script" not in strPage
    assert "<img" not in strPage
    assert "<iframe" not in strPage
    assert "&lt;script&gt;alert(1)&lt;/script&gt;" in strPage
    assert not re.search(r"""href=["']?(javascript|data):""", strPage, re.I)


def test_the_answer_is_in_a_container_that_scrolls(show):
    strPage = show("The answer is four.")
    assert re.search(r'<div style="overflow-x: auto;">\s*<p>The answer is four.</p>\s*</div>', strPage)


# ---- the site's own pages and the rating page
def test_a_page_of_the_site_may_hold_html(client, site_app, tmp_path, monkeypatch):
    (tmp_path / "home.md").write_text("# Home\n\n<b class='x'>bold</b>\n")
    monkeypatch.setattr(site_app.app, "markdown_dir", str(tmp_path))
    assert "<b class='x'>bold</b>" in client.get("/").get_data(as_text=True)


def test_the_rating_page_shows_an_answer_as_the_site_does(tmp_path):
    strAnswer = "Check:\n- one\n\n| a | b |\n|---|---|\n| 1 | 2 |\n"
    dctQuestion = {"question_id": "Q01", "kind": "factual", "question": "q"}
    write_json(str(tmp_path / "prompts" / "Q01.json"), dctQuestion | {"ids": ["a"], "prompt": "p"})
    write_json(str(tmp_path / "answers" / "Q01_m.json"),
               {"question_id": "Q01", "model": "m", "answer": strAnswer})
    strPage = create_app(str(tmp_path), [dctQuestion]).test_client().get("/").text
    assert get_answer_html(strAnswer) in strPage
