# ABOUTME: Tests the links that the numbers in a numbered answer become on the results page (plan 4.1b).
# ABOUTME: The number shown is the row of the chunk's source in the source list under the answer.

import json
import re

import pytest

NEWS = "news_78"
MESSAGE = "30SXLjAf9AY"
NEWS_URL = "http://cozybuilders.org/newsletters/news_78.pdf"
MESSAGE_URL = "https://groups.google.com/g/cozy_builders/c/30SXLjAf9AY"
NO_ADDRESS = "!!!"
HOSTILE = """Look <script>alert(1)</script> [1] and <img src=x onerror=alert(1)> [2]

[a](javascript:alert(1)) and [b](JaVaScRiPt:alert(1)) [3]
"""


def entry(strId, strSource, strScore=None):
    dctEntry = {"id": strId, "source": strSource}
    return dctEntry if strScore is None else dict(dctEntry, score=strScore)


# chunks 1 and 2 of the first source, chunk 3 of the second
PROVIDED = [entry("n0", NEWS, "0.80"), entry("n1", NEWS, "0.70"), entry("m0", MESSAGE, "0.60")]


def job(strAnswer, strType="new", lstProvided=PROVIDED, bNumbered=True):
    dctResult = {"answer": strAnswer, "type": strType, "provided_docs": lstProvided,
                 "numbered_docs": bNumbered}
    if strType == "new":
        dctResult["related_docs"] = [entry("r0", "news_79", "0.50")]
    return {"process_id": "done", "status": "complete", "created": 1.0, "elapsed": 2.5,
            "type": strType, "query": "q", "result": dctResult}


@pytest.fixture
def show(client, jobs_dir):
    """Gives the answer and the provided docs of the results page of a job."""
    def get_page(dctJob):
        (jobs_dir / "done.json").write_text(json.dumps(dctJob))
        response = client.get("/cozyrag/done/processid")
        assert response.status_code == 200
        strPage = response.get_data(as_text=True)
        strAnswer = re.search(r'<div style="overflow-x: auto;">(.*?)</div>', strPage, re.S).group(1)
        strProvided = strPage.split("<h5>Provided Docs</h5>")[1].split("</table>")[0]
        return strAnswer, strProvided
    return get_page


def links(strHtml):
    """The links of the html: their address, title and text."""
    return re.findall(r'<a href="([^"]*)" title="([^"]*)" target="_blank" rel="noopener">([^<]*)</a>',
                      strHtml)


NEWS_LINK = (NEWS_URL, "Cozy Newsletters Number 78", "[1]")
MESSAGE_LINK = (MESSAGE_URL, "Cozy Builders Google Group Message 30SXLjAf9AY", "[2]")


def test_a_number_is_shown_as_the_row_of_its_source(show):
    strAnswer, strProvided = show(job("Use flox [3]."))
    assert links(strAnswer) == [MESSAGE_LINK]
    assert re.search(r"\[1\]\s*<a href='" + NEWS_URL, strProvided)
    assert re.search(r"\[2\]\s*<a href='" + MESSAGE_URL, strProvided)


def test_two_chunks_of_one_source_are_shown_once(show):
    strAnswer, _ = show(job("Use flox [1][2]."))
    assert links(strAnswer) == [NEWS_LINK]
    assert re.sub(r"<[^>]+>", "", strAnswer).strip() == "Use flox [1]."


@pytest.mark.parametrize("strMarks", ["[1][3]", "[1, 3]", "[1] [3]", "[3][1][2]"])
def test_marks_of_two_sources_are_shown_once_each_in_the_order_written(show, strMarks):
    strAnswer, _ = show(job(f"Use flox {strMarks}."))
    lstExpected = [NEWS_LINK, MESSAGE_LINK]
    if strMarks.startswith("[3]"):
        lstExpected = [MESSAGE_LINK[:2] + ("[2]",), NEWS_LINK[:2] + ("[1]",)]
    assert links(strAnswer) == lstExpected


def test_a_number_in_two_sentences_is_shown_in_both(show):
    strAnswer, _ = show(job("Use flox [1]. Sand it first [1]."))
    assert links(strAnswer) == [NEWS_LINK, NEWS_LINK]


def test_a_number_that_names_no_chunk_is_not_on_the_page(show):
    strAnswer, _ = show(job("Use flox [9] before the layup [0]. Then sand."))
    assert links(strAnswer) == []
    assert "[9]" not in strAnswer and "[0]" not in strAnswer
    assert re.search(r"Use flox\s+before the layup\s*\. Then sand\.", strAnswer)


def test_a_number_in_code_stays_as_written(show):
    strAnswer, _ = show(job("Type `a[1]` here.\n\n```\nb[2]\n```\n"))
    assert links(strAnswer) == []
    assert "<code>a[1]</code>" in strAnswer
    assert "b[2]" in strAnswer


def test_a_source_without_an_address_has_its_number_and_no_link(show):
    strAnswer, strProvided = show(job("Use flox [1].", lstProvided=[entry("x0", NO_ADDRESS, "0.80")]))
    assert links(strAnswer) == []
    assert "Use flox [1]." in strAnswer
    assert "[1]" in strProvided


def test_an_answer_that_is_not_numbered_is_not_touched(show):
    strAnswer, strProvided = show(job("Use flox [1].", bNumbered=False))
    assert links(strAnswer) == []
    assert "Use flox [1]." in strAnswer
    assert "[1]" not in strProvided


def test_an_answer_of_before_the_setting_is_not_touched(show):
    dctJob = job("Use flox [1].")
    del dctJob["result"]["numbered_docs"]
    strAnswer, strProvided = show(dctJob)
    assert links(strAnswer) == []
    assert "[1]" not in strProvided


def test_the_stored_answer_is_not_changed(show, jobs_dir):
    dctJob = job("Use flox [3].")
    show(dctJob)
    assert json.loads((jobs_dir / "done.json").read_text())["result"] == dctJob["result"]


def test_hostile_text_still_gives_no_tag_and_no_script_link(show):
    strAnswer, _ = show(job(HOSTILE))
    assert "<script" not in strAnswer and "<img" not in strAnswer
    assert not re.search(r"""href=["']?(javascript|data):""", strAnswer, re.I)
    assert links(strAnswer) == [NEWS_LINK, NEWS_LINK, MESSAGE_LINK]


@pytest.mark.parametrize("strType", ["revise", "followup"])
def test_a_revise_and_a_followup_link_by_their_own_list(show, strType):
    lstProvided = [entry("m0", MESSAGE), entry("n0", NEWS), entry("m1", MESSAGE)]
    strAnswer, strProvided = show(job("Use flox [2]. Sand [3].", strType, lstProvided))
    assert links(strAnswer) == [NEWS_LINK[:2] + ("[2]",), MESSAGE_LINK[:2] + ("[1]",)]
    assert re.search(r"\[1\]\s*<a href='" + MESSAGE_URL, strProvided)


# ---- a link the model defines itself (plan 4.1b)
DEFINITION = "Use flox [1].\n\n[1]: https://example.com\n"


def test_a_definition_in_a_numbered_answer_does_not_change_where_a_number_leads(show):
    strAnswer, _ = show(job(DEFINITION))
    # the definition is shown as text, and its number too leads to our source
    assert links(strAnswer) == [NEWS_LINK, NEWS_LINK]
    assert "https://example.com" in strAnswer
    assert 'href="https://example.com"' not in strAnswer


def test_a_definition_makes_no_link_in_an_answer_that_is_not_numbered(show):
    strAnswer, _ = show(job(DEFINITION, bNumbered=False))
    assert "<a " not in strAnswer
    assert "Use flox [1]." in strAnswer
