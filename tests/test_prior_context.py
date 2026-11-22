# ABOUTME: Tests which documents revise and follow-up prompts and their records carry, in order.
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


# ---- a follow-up
NO_CUTOFF = 10.
ALL_CUT_OFF = 0.


@pytest.fixture
def retrieved(processor, collection):
    """The 60 documents retrieved for a follow-up question."""
    lstEmbeddings = collection.get(ids=["news_7810"], include=["embeddings"])["embeddings"]
    dctQuery = collection.query(query_embeddings=lstEmbeddings, n_results=60)
    processor.get_query_results = lambda question: dctQuery
    return dctQuery


def followup_on(dctResult):
    return {"type": "followup", "query": "and how many doors", "result": dctResult}


def followup_data(lstProvided, lstRelated):
    return followup_on(revise_data(lstProvided, lstRelated)["result"])


def set_cutoff(processor, fMaxDistance):
    processor.set_docs_params(max_distance=fMaxDistance, min_documents=5, max_documents=60,
                              max_draft_documents=15)


def contents(strPrompt):
    """The previous and the additional content of a follow-up prompt."""
    strPrevious, strAdditional = strPrompt.split("PREVIOUS CONTENT: ")[1].split(
        "ADDITIONAL_CONTENT: ")
    return strPrevious.strip(), strAdditional.strip()


def joined(lstTexts):
    return "\n\n".join(lstTexts).strip()


def test_followup_previous_content_is_the_provided_documents(processor, collection, retrieved):
    processor.process_question(followup_data(PROVIDED, RELATED))
    strPrevious, _ = contents(processor.lstPrompts[0])
    assert strPrevious == joined(texts_of(collection, PROVIDED))


@pytest.mark.parametrize("fMaxDistance, intExpected", [(NO_CUTOFF, 15), (ALL_CUT_OFF, 5)])
def test_followup_additional_content_is_cut_like_a_first_answer(processor, retrieved,
                                                                fMaxDistance, intExpected):
    set_cutoff(processor, fMaxDistance)
    processor.process_question(followup_data(PROVIDED, RELATED))
    _, strAdditional = contents(processor.lstPrompts[0])
    assert strAdditional == joined(retrieved["documents"][0][:intExpected])


def test_followup_record_is_previous_then_additional(processor, retrieved):
    set_cutoff(processor, NO_CUTOFF)
    dctRecord = processor.process_question(followup_data(PROVIDED, RELATED))
    assert [d["id"] for d in dctRecord["provided_docs"]] == PROVIDED + retrieved["ids"][0][:15]
    assert "related_docs" not in dctRecord


def test_followup_record_has_no_document_twice(processor, retrieved):
    set_cutoff(processor, NO_CUTOFF)
    lstRetrieved = retrieved["ids"][0]
    lstProvided = [PROVIDED[0], lstRetrieved[2]]
    dctRecord = processor.process_question(followup_data(lstProvided, RELATED))
    assert [d["id"] for d in dctRecord["provided_docs"]] == (
        lstProvided + [strId for strId in lstRetrieved[:15] if strId != lstRetrieved[2]])


def test_second_followup_adds_no_more_than_the_maximum(processor, collection, retrieved):
    set_cutoff(processor, NO_CUTOFF)
    dctFirst = processor.process_question(followup_data(PROVIDED, RELATED))
    lstEmbeddings = collection.get(ids=["30SXLjAf9AY0"], include=["embeddings"])["embeddings"]
    dctQuery = collection.query(query_embeddings=lstEmbeddings, n_results=60)
    processor.get_query_results = lambda question: dctQuery

    dctSecond = processor.process_question(followup_on(dctFirst))

    lstFirst = [d["id"] for d in dctFirst["provided_docs"]]
    lstSecond = [d["id"] for d in dctSecond["provided_docs"]]
    strPrevious, strAdditional = contents(processor.lstPrompts[1])
    assert lstSecond[:len(lstFirst)] == lstFirst
    assert 0 < len(lstSecond) - len(lstFirst) <= 15
    assert strPrevious == joined(texts_of(collection, lstFirst))
    assert strAdditional == joined(dctQuery["documents"][0][:15])
