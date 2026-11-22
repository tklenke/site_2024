# ABOUTME: Tests that revise and follow-up prompts carry the full text of every prior document.
# ABOUTME: Reads real documents from the local Chroma service; only the model call is recorded.

import pytest


@pytest.fixture
def prior_docs(collection):
    """Three real documents: the result of a collection.get()."""
    return collection.get(limit=3)


def job_data(strType, dctPriorDocs):
    lstDocs = [{"id": strId} for strId in dctPriorDocs["ids"]]
    return {"type": strType, "query": "how many seats does the cozy have",
            "result": {"answer": "It has four seats.", "provided_docs": lstDocs[:2],
                       "related_docs": lstDocs[2:]}}


def test_revise_prompt_has_every_prior_document(processor, prior_docs):
    processor.process_question(job_data("revise", prior_docs))
    for strText in prior_docs["documents"]:
        assert strText in processor.lstPrompts[0]


def test_followup_prompt_has_every_prior_document(processor, collection, prior_docs):
    lstEmbeddings = collection.get(limit=1, offset=100, include=["embeddings"])["embeddings"]
    dctQuery = collection.query(query_embeddings=lstEmbeddings, n_results=5)
    processor.get_query_results = lambda question: dctQuery

    processor.process_question(job_data("followup", prior_docs))

    for strText in prior_docs["documents"] + dctQuery["documents"][0]:
        assert strText in processor.lstPrompts[0]


# ---- the order of a revise
# the order of the record; not the order in which collection.get() returns them
PROVIDED = ["cb__ref_info_-_kitplane___html101", "ttXB7VHdy1w0", "cb__ref_info_-_kitplane___html100"]
RELATED = ["qcyg9TEAGXE0", "30SXLjAf9AY1", "30SXLjAf9AY0"]


def revise_data(lstProvided, lstRelated):
    return {"type": "revise", "query": "how many seats does the cozy have",
            "result": {"answer": "It has four seats.",
                       "provided_docs": [{"id": strId} for strId in lstProvided],
                       "related_docs": [{"id": strId} for strId in lstRelated]}}


def texts_of(collection, lstIds):
    return [collection.get(ids=[strId])["documents"][0] for strId in lstIds]


def revise(processor, lstProvided, lstRelated):
    """The prompt sent for a revise of a job with these chunks, and its record."""
    dctRecord = processor.process_question(revise_data(lstProvided, lstRelated))
    return processor.lstPrompts[0], dctRecord


def test_the_collection_returns_documents_in_another_order(collection):
    assert collection.get(ids=PROVIDED + RELATED)["ids"] != PROVIDED + RELATED


def test_revise_prompt_has_the_documents_in_rank_order(processor, collection):
    strPrompt, _ = revise(processor, PROVIDED, RELATED)
    assert "\n\n".join(texts_of(collection, PROVIDED + RELATED)) in strPrompt


def test_revise_record_lists_the_documents_in_rank_order(processor):
    _, dctRecord = revise(processor, PROVIDED, RELATED)
    assert [d["id"] for d in dctRecord["provided_docs"]] == PROVIDED + RELATED
    assert "related_docs" not in dctRecord


def test_revise_record_keeps_the_source_of_each_document(processor):
    _, dctRecord = revise(processor, PROVIDED, RELATED)
    assert [d["source"] for d in dctRecord["provided_docs"]] == [
        "cb__ref_info_-_kitplane___html", "ttXB7VHdy1w", "cb__ref_info_-_kitplane___html",
        "qcyg9TEAGXE", "30SXLjAf9AY", "30SXLjAf9AY"]


def test_a_document_listed_twice_is_given_once_at_its_first_place(processor, collection):
    strPrompt, dctRecord = revise(processor, PROVIDED, [PROVIDED[0]] + RELATED)
    assert [d["id"] for d in dctRecord["provided_docs"]] == PROVIDED + RELATED
    assert strPrompt.count(texts_of(collection, PROVIDED[:1])[0]) == 1


def test_a_document_no_longer_in_the_collection_is_left_out(processor, collection):
    strPrompt, dctRecord = revise(processor, PROVIDED, ["nosuchdocument0"] + RELATED)
    assert [d["id"] for d in dctRecord["provided_docs"]] == PROVIDED + RELATED
    assert "\n\n".join(texts_of(collection, PROVIDED + RELATED)) in strPrompt
