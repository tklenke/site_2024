# ABOUTME: Tests the setting that numbers the chunks of a prompt, and the record of a numbered answer.
# ABOUTME: Reads real documents from the local Chroma service; only the model call is recorded.

import configparser
from pathlib import Path

import pytest

FWWW = Path(__file__).resolve().parent.parent / "fwww"
PROVIDED = ["cb__ref_info_-_kitplane___html101", "ttXB7VHdy1w0", "cb__ref_info_-_kitplane___html100"]
RELATED = ["qcyg9TEAGXE0", "30SXLjAf9AY1", "30SXLjAf9AY0"]


def test_the_setting_is_on_on_the_site():
    cfg = configparser.ConfigParser()
    cfg.read(FWWW / "site.ini")
    assert cfg.getboolean("PROMPTS", "NUMBER_DOCS") is True


def test_the_site_gives_the_setting_to_the_job_thread(site_app):
    # the settings of the tests switch it on, so that a setting not given would show
    assert site_app.FPThread.numbered is True


@pytest.fixture
def retrieved(processor, collection):
    """The 60 documents retrieved for a question."""
    lstEmbeddings = collection.get(ids=["news_7810"], include=["embeddings"])["embeddings"]
    dctQuery = collection.query(query_embeddings=lstEmbeddings, n_results=60)
    processor.get_query_results = lambda question: dctQuery
    processor.set_docs_params(max_distance=10., min_documents=5, max_documents=60,
                              max_draft_documents=15)
    return dctQuery


def prior_result():
    return {"answer": "It has four seats.",
            "provided_docs": [{"id": strId} for strId in PROVIDED],
            "related_docs": [{"id": strId} for strId in RELATED]}


def ask(processor, strType):
    """The prompt sent for a job of this type, and its record."""
    dctRecord = processor.process_question({"type": strType, "query": "how many seats",
                                            "result": prior_result()})
    return processor.lstPrompts[-1], dctRecord


def texts_of(collection, dctRecord):
    lstIds = [d["id"] for d in dctRecord["provided_docs"]]
    return [collection.get(ids=[strId])["documents"][0] for strId in lstIds]


@pytest.mark.parametrize("strType", ["new", "revise", "followup"])
def test_the_record_says_the_answer_was_not_numbered(processor, retrieved, strType):
    strPrompt, dctRecord = ask(processor, strType)
    assert dctRecord["numbered_docs"] is False
    assert "[1] " not in strPrompt


@pytest.mark.parametrize("strType", ["new", "revise", "followup"])
def test_a_numbered_prompt_gives_each_chunk_the_number_of_its_place_in_the_record(
        processor, collection, retrieved, strType):
    processor.set_doc_numbering(True)
    strPrompt, dctRecord = ask(processor, strType)
    assert dctRecord["numbered_docs"] is True
    lstTexts = texts_of(collection, dctRecord)
    assert len(lstTexts) > 5
    for intNumber, strText in enumerate(lstTexts, 1):
        assert f"[{intNumber}] {strText}" in strPrompt
    assert f"[{len(lstTexts) + 1}] " not in strPrompt
