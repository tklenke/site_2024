# ABOUTME: Tests the trial of numbered chunks: the check of the saved prompts and the run.
# ABOUTME: Reads real documents from the local Chroma service; the model is a local stand-in.

import json

import openai
import pytest

from cite_trial import MODEL, check_prompts, run_trial
from src.llm_functions import build_prompt, get_docs_in_order

IDS = ["cb__ref_info_-_kitplane___html101", "ttXB7VHdy1w0", "qcyg9TEAGXE0"]


def completion(strAnswer="It has four seats [2]."):
    return {"id": "c1", "object": "chat.completion", "created": 1, "model": f"{MODEL}-dated",
            "choices": [{"index": 0, "finish_reason": "stop",
                         "message": {"role": "assistant", "content": strAnswer}}],
            "usage": {"prompt_tokens": 4000, "completion_tokens": 300, "total_tokens": 4300}}


def client_of(server):
    return openai.OpenAI(api_key="unused", base_url=server.strUrl, max_retries=0, timeout=5)


@pytest.fixture
def saved(collection):
    """The saved prompt record of a question, as the evaluation wrote it."""
    def make(strId, lstIds=IDS):
        lstTexts = get_docs_in_order(collection, lstIds)["documents"]
        strQuestion = f"question {strId}"
        return {"question_id": strId, "kind": "how", "question": strQuestion, "ids": lstIds,
                "prompt": build_prompt({"type": "new", "query": strQuestion}, lstTexts)}
    return make


def test_a_prompt_the_fetched_chunks_still_give_is_numbered(collection, saved):
    dctSaved = saved("Q01")
    dctPrompts, dctLeftOut = check_prompts(collection, [dctSaved])
    lstTexts = get_docs_in_order(collection, IDS)["documents"]
    assert dctPrompts == {"Q01": build_prompt({"type": "new", "query": "question Q01"}, lstTexts,
                                              numbered=True)}
    assert dctLeftOut == {}


def test_a_prompt_with_a_chunk_no_longer_in_the_collection_is_left_out(collection, saved):
    dctSaved = saved("Q01") | {"ids": IDS + ["nosuchdocument0"]}
    dctPrompts, dctLeftOut = check_prompts(collection, [dctSaved])
    assert dctPrompts == {}
    assert dctLeftOut == {"Q01": "not in the collection: nosuchdocument0"}


def test_a_prompt_the_fetched_chunks_no_longer_give_is_left_out(collection, saved):
    dctSaved = saved("Q01")
    dctSaved["prompt"] = dctSaved["prompt"].replace("kitplane", "kit plane", 1) + " changed"
    dctPrompts, dctLeftOut = check_prompts(collection, [dctSaved])
    assert dctPrompts == {}
    assert dctLeftOut == {"Q01": "the chunks give another prompt than the saved one"}


def test_the_numbered_prompt_is_sent_and_the_answer_saved_in_its_own_directory(
        collection, saved, start_openai_server, tmp_path):
    server = start_openai_server(200, completion())
    run_trial(collection, client_of(server), [saved("Q01")], tmp_path)
    dctPrompts, _ = check_prompts(collection, [saved("Q01")])
    assert [(body["model"], body["messages"][0]["content"]) for _, body in server.lstRequests] == \
        [(MODEL, dctPrompts["Q01"])]
    dctAnswer = json.loads((tmp_path / f"Q01_{MODEL}.json").read_text())
    assert dctAnswer["question_id"] == "Q01"
    assert dctAnswer["ids"] == IDS
    assert dctAnswer["numbered_docs"] is True
    assert dctAnswer["prompt"] == dctPrompts["Q01"]
    assert dctAnswer["answer"] == "It has four seats [2]."
    assert dctAnswer["cost"] > 0


def test_every_prompt_is_checked_before_any_call(collection, saved, start_openai_server,
                                                 tmp_path, capsys):
    server = start_openai_server(200, completion())
    lstSaved = [saved("Q01"), saved("Q02") | {"ids": ["nosuchdocument0"]}, saved("Q03")]
    dctLeftOut = run_trial(collection, client_of(server), lstSaved, tmp_path)
    assert dctLeftOut == {"Q02": "not in the collection: nosuchdocument0"}
    assert len(server.lstRequests) == 2
    assert sorted(p.name for p in tmp_path.iterdir()) == [f"Q01_{MODEL}.json", f"Q03_{MODEL}.json"]
    lstLines = capsys.readouterr().out.splitlines()
    assert lstLines[0] == "Q02: left out, not in the collection: nosuchdocument0"
    assert lstLines[1] == "2 of 3 questions to ask"
    assert [strLine.split(":")[0] for strLine in lstLines[2:]] == ["Q01", "Q03"]


def test_an_answer_already_saved_is_not_paid_again(collection, saved, start_openai_server,
                                                   tmp_path, capsys):
    server = start_openai_server(200, completion())
    run_trial(collection, client_of(server), [saved("Q01")], tmp_path)
    run_trial(collection, client_of(server), [saved("Q01")], tmp_path)
    assert len(server.lstRequests) == 1
    assert capsys.readouterr().out.splitlines()[-1] == "Q01: kept"
