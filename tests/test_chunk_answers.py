# ABOUTME: Tests the look at answers from the chunk-size variants (plan 2.6): the text budget,
# ABOUTME: the prompts, the run and the blind sheets. Reads the real collection; the model is a local stand-in.

import json
import random

import openai
import pytest

from chunk_answers import (MODEL, RUNS, count_words, get_prompt_record, make_sheet,
                           run_questions, select_within_budget, write_sheets)
from src.llm_functions import build_prompt

CHUNK = "qcyg9TEAGXE0"


def completion(strAnswer):
    return {"id": "c1", "object": "chat.completion", "created": 1, "model": f"{MODEL}-dated",
            "choices": [{"index": 0, "finish_reason": "stop",
                         "message": {"role": "assistant", "content": strAnswer}}],
            "usage": {"prompt_tokens": 5000, "completion_tokens": 300, "total_tokens": 5300}}


def client_of(server):
    return openai.OpenAI(api_key="unused", base_url=server.strUrl, max_retries=0, timeout=5)


@pytest.fixture
def embed(collection):
    """Gives, for any question, the stored vector of one real chunk, so that chunk is found first."""
    lstVector = collection.get(ids=[CHUNK], include=["embeddings"])["embeddings"][0]
    return lambda strQuestion: [list(lstVector)]


def test_the_words_of_a_chunk_are_counted_without_its_prefix():
    assert count_words("search_document: one two  three\nfour") == 4
    assert count_words("one two") == 2


def test_chunks_are_taken_in_order_while_their_words_fit_the_budget():
    lstDocs = ["a b c", "d e", "f g h i", "j"]
    assert select_within_budget(lstDocs, 5) == (2, 5)
    assert select_within_budget(lstDocs, 9) == (3, 9)


def test_the_first_chunk_that_does_not_fit_ends_the_list_and_none_after_it_is_taken():
    assert select_within_budget(["a b", "c d e f", "g"], 4) == (1, 2)


def test_a_first_chunk_larger_than_the_budget_is_refused():
    with pytest.raises(ValueError, match="budget"):
        select_within_budget(["a b c d"], 3)


def test_the_prompt_is_the_first_answer_without_numbers_from_the_chunks_within_the_budget(
        collection, embed):
    dctRecord = get_prompt_record(collection, embed, "how is it built", 600)
    rAll = collection.query(query_embeddings=embed("x"), n_results=60)
    lstDocs = rAll["documents"][0]
    intDocs, intWords = select_within_budget(lstDocs, 600)
    assert dctRecord["ids"][0] == CHUNK
    assert dctRecord["ids"] == rAll["ids"][0][:intDocs]
    assert dctRecord["docs"] == lstDocs[:intDocs]
    assert dctRecord["words"] == intWords <= 600
    assert dctRecord["prompt"] == build_prompt({"type": "new", "query": "how is it built"},
                                               lstDocs[:intDocs])
    assert "[1]" not in dctRecord["prompt"]


def test_each_run_is_asked_once_and_the_two_runs_of_a_share_one_prompt(
        collection, embed, start_openai_server, tmp_path):
    server = start_openai_server(200, completion("Use the plans."))
    dctCollections = {strVariant: collection for strVariant in "ABCDE"}
    lstQuestions = [{"question_id": "Q99", "question": "how is it built"}]
    run_questions(dctCollections, embed, client_of(server), lstQuestions, tmp_path, 600)
    assert len(server.lstRequests) == len(RUNS) == 6
    assert {body["model"] for _, body in server.lstRequests} == {MODEL}
    dctA = json.loads((tmp_path / "answers" / "Q99_A.json").read_text())
    dctA2 = json.loads((tmp_path / "answers" / "Q99_A2.json").read_text())
    assert dctA["prompt"] == dctA2["prompt"]
    assert dctA2["variant"] == "A"
    assert dctA["answer"] == "Use the plans."
    assert dctA["words"] <= 600
    assert dctA["cost"] > 0


def test_an_answer_already_saved_is_not_paid_for_again(collection, embed, start_openai_server,
                                                        tmp_path):
    server = start_openai_server(200, completion("Use the plans."))
    dctCollections = {strVariant: collection for strVariant in "ABCDE"}
    lstQuestions = [{"question_id": "Q99", "question": "how is it built"}]
    run_questions(dctCollections, embed, client_of(server), lstQuestions, tmp_path, 600)
    run_questions(dctCollections, embed, client_of(server), lstQuestions, tmp_path, 600)
    assert len(server.lstRequests) == 6


def answer_record(strRun, lstDocs, strAnswer):
    return {"question_id": "Q99", "question": "how is it built", "run": strRun,
            "variant": strRun[0], "docs": lstDocs, "answer": strAnswer}


def test_a_sheet_shows_each_answer_under_a_letter_and_the_pooled_text_once():
    lstRecords = [answer_record(strRun, ["search_document: shared text", f"only {strRun}"],
                                f"answer number {i}") for i, strRun in enumerate(RUNS)]
    strSheet, dctKey = make_sheet(lstRecords, random.Random(1))
    assert sorted(dctKey) == list("UVWXYZ")
    assert sorted(dctKey.values()) == sorted(RUNS)
    for strLetter, strRun in dctKey.items():
        assert f"## Answer {strLetter}\n\nanswer number {RUNS.index(strRun)}\n" in strSheet
    assert strSheet.count("shared text") == 1
    for strRun in RUNS:
        assert strSheet.count(f"\nonly {strRun}\n") == 1
    strBeforeText = strSheet.split("# Pooled text")[0]
    for strName in ("variant", "A2", "words250"):
        assert strName not in strBeforeText


def test_the_sheets_are_written_once_and_the_key_is_never_overwritten(tmp_path):
    pathAnswers = tmp_path / "answers"
    pathAnswers.mkdir()
    for strRun in RUNS:
        (pathAnswers / f"Q99_{strRun}.json").write_text(
            json.dumps(answer_record(strRun, ["some text"], f"answer of {strRun}")))
    write_sheets(tmp_path, random.Random(2))
    dctKey = json.loads((tmp_path / "key.json").read_text())
    assert sorted(dctKey["Q99"].values()) == sorted(RUNS)
    assert "## Answer U" in (tmp_path / "sheets" / "Q99.md").read_text()
    with pytest.raises(FileExistsError):
        write_sheets(tmp_path, random.Random(3))
    assert json.loads((tmp_path / "key.json").read_text()) == dctKey
