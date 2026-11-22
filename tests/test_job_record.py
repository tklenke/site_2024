# ABOUTME: Tests which chunks a job record keeps and which sources the results page lists.
# ABOUTME: The record has every chunk in the order retrieved; the page has one row per source.

import json
import re

import pytest

from src.site_functions import get_job_for_display, url_from_source

NEWS_78 = "news_78"
NEWS_79 = "news_79"
MESSAGE = "30SXLjAf9AY"
LONG_DOCUMENT = "cb__ref_info_-_kitplane___html"


def entry(strId, strSource, strScore=None):
    dctEntry = {"id": strId, "source": strSource}
    return dctEntry if strScore is None else dict(dctEntry, score=strScore)


def job(strType, dctResult):
    return {"process_id": "abc", "status": "complete", "created": 1.0, "elapsed": 2.5,
            "type": strType, "query": "how many seats",
            "result": {"answer": "Four.", "type": strType, **dctResult}}


# the first answer: several chunks of one source among the provided and the related ones
FIRST_ANSWER = job("new", {
    "provided_docs": [entry("a1", NEWS_78, "0.80"), entry("b1", MESSAGE, "0.75"),
                      entry("a2", NEWS_78, "0.70")],
    "related_docs": [entry("a3", NEWS_78, "0.60"), entry("c1", NEWS_79, "0.55"),
                     entry("a4", NEWS_78, "0.50")]})
REVISE = job("revise", {
    "provided_docs": [entry("a1", NEWS_78), entry("b1", MESSAGE), entry("a2", NEWS_78)]})


# ---- the record
@pytest.fixture
def query_result(collection):
    """A real query result with several chunks from one source."""
    lstEmbeddings = collection.get(limit=1, offset=100, where={"source": LONG_DOCUMENT},
                                   include=["embeddings"])["embeddings"]
    dctQuery = collection.query(query_embeddings=lstEmbeddings, n_results=60)
    lstSources = [dctMetadata["source"] for dctMetadata in dctQuery["metadatas"][0]]
    assert len(set(lstSources[:15])) < 15
    assert len(set(lstSources[15:])) < 45
    return dctQuery


def test_record_of_a_first_answer_has_every_chunk_in_order(processor, query_result):
    processor.get_query_results = lambda question: query_result
    dctRecord = processor.process_question({"type": "new", "query": "how many seats"})

    intProvided = dctRecord["number provided docs"]
    assert [d["id"] for d in dctRecord["provided_docs"]] == query_result["ids"][0][:intProvided]
    assert [d["id"] for d in dctRecord["related_docs"]] == query_result["ids"][0][intProvided:]
    assert len(dctRecord["provided_docs"]) == intProvided


def test_record_entries_keep_source_and_score(processor, query_result):
    processor.get_query_results = lambda question: query_result
    dctRecord = processor.process_question({"type": "new", "query": "how many seats"})

    lstEntries = dctRecord["provided_docs"] + dctRecord["related_docs"]
    assert [d["source"] for d in lstEntries] == [m["source"] for m in query_result["metadatas"][0]]
    assert [d["score"] for d in lstEntries] == [f"{1 - f:.2f}" for f in query_result["distances"][0]]


# ---- the display
def sources(dctJob, strKey):
    return [d["source"] for d in dctJob["result"][strKey]]


def test_first_answer_is_displayed_with_one_entry_per_source():
    dctShown = get_job_for_display(FIRST_ANSWER)
    assert dctShown["result"]["provided_docs"] == [entry("a1", NEWS_78, "0.80"),
                                                   entry("b1", MESSAGE, "0.75")]
    assert dctShown["result"]["related_docs"] == [entry("a3", NEWS_78, "0.60"),
                                                  entry("c1", NEWS_79, "0.55")]


def test_revise_is_displayed_with_one_entry_per_source():
    dctShown = get_job_for_display(REVISE)
    assert dctShown["result"]["provided_docs"] == [entry("a1", NEWS_78), entry("b1", MESSAGE)]
    assert "related_docs" not in dctShown["result"]


def test_the_highest_score_of_a_source_is_displayed():
    dctJob = job("new", {"provided_docs": [entry("a1", NEWS_78, "0.60"),
                                           entry("a2", NEWS_78, "0.80")]})
    assert get_job_for_display(dctJob)["result"]["provided_docs"] == [entry("a2", NEWS_78, "0.80")]


@pytest.mark.parametrize("lstScores", [(None, "0.70"), ("0.70", None)])
def test_entries_with_and_without_a_score_are_displayed_once(lstScores):
    dctJob = job("followup", {"provided_docs": [entry("a1", NEWS_78, lstScores[0]),
                                                entry("a2", NEWS_78, lstScores[1])]})
    dctShown = get_job_for_display(dctJob)
    assert [d["score"] for d in dctShown["result"]["provided_docs"]] == ["0.70"]


@pytest.mark.parametrize("dctJob", [FIRST_ANSWER, REVISE])
def test_the_record_is_not_changed_by_displaying_it(dctJob):
    strBefore = json.dumps(dctJob)
    get_job_for_display(dctJob)
    assert json.dumps(dctJob) == strBefore


def test_an_unfinished_job_is_displayed_without_a_result():
    assert get_job_for_display({"status": "start"})["result"] == {}


@pytest.mark.parametrize("strPage", ["processid", "status"])
@pytest.mark.parametrize("dctJob, lstExpected", [
    (FIRST_ANSWER, [NEWS_78, MESSAGE, NEWS_78, NEWS_79]), (REVISE, [NEWS_78, MESSAGE])])
def test_results_page_has_one_row_per_source(client, jobs_dir, strPage, dctJob, lstExpected):
    (jobs_dir / "abc.json").write_text(json.dumps(dctJob))
    response = client.get(f"/cozyrag/abc/{strPage}")
    strHtml = response.get_json()["result_html"] if strPage == "status" else response.text
    lstLinks = re.findall(r"<a href='([^']*)'>", strHtml)
    assert lstLinks == [url_from_source(strSource)[0] for strSource in lstExpected]
