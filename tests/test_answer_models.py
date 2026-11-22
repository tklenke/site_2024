# ABOUTME: Tests the evaluation harness: the questions, the documents, the calls and what is saved.
# ABOUTME: The real OpenAI client calls a local server; the retrieval runs on the real collection.

import configparser
import json

import openai
import pytest

from answer_models import MODEL_PRICES, ask_model, create_retriever, get_prompt_record, \
    read_questions, run_questions
from src.llm_functions import FileProcessorThread

QUESTION = {"question_id": "Q01", "question": "how many seats, and \"doors\""}
OTHER_QUESTION = {"question_id": "Q03", "question": "bolt torque"}
MODEL = "gpt-4o-mini"


def completion(strAnswer="It has four seats.", dctDetails=None, strFinish="stop"):
    dctUsage = {"prompt_tokens": 4000, "completion_tokens": 300, "total_tokens": 4300}
    if dctDetails is not None:
        dctUsage["completion_tokens_details"] = dctDetails
    return {"id": "c1", "object": "chat.completion", "created": 1, "model": f"{MODEL}-dated",
            "choices": [{"index": 0, "finish_reason": strFinish,
                         "message": {"role": "assistant", "content": strAnswer}}],
            "usage": dctUsage}


def client_of(server):
    return openai.OpenAI(api_key="unused", base_url=server.strUrl, max_retries=0, timeout=5)


@pytest.fixture
def retriever(processor, collection):
    """The processor, with an embedder that gives the embedding of a document in the collection."""
    lstEmbeddings = collection.get(limit=1, include=["embeddings"])["embeddings"]

    class Embedder:
        lstInputs = []

        def embed(self, model, input):
            self.lstInputs.append(input)
            return {"embeddings": lstEmbeddings}

    processor.ollamaclient = Embedder()
    processor.ollamaclient.lstInputs = []
    processor.embed_model = "nomic-embed-text"
    processor.set_embed_prefix("search_query:")
    return processor


def test_questions_of_a_batch_are_read_in_order(tmp_path):
    pathCsv = tmp_path / "questions.csv"
    pathCsv.write_text('question_id,use,kind,question\nQ02,batch2,broad,two\n'
                       'Q03,batch1,broad,"three, quoted"\nQ01,batch1,factual,one\n')
    assert read_questions(pathCsv, "batch1") == [
        {"question_id": "Q03", "kind": "broad", "question": "three, quoted"},
        {"question_id": "Q01", "kind": "factual", "question": "one"}]


def test_an_unknown_batch_is_refused(tmp_path):
    pathCsv = tmp_path / "questions.csv"
    pathCsv.write_text("question_id,use,kind,question\nQ02,batch2,broad,two\n")
    with pytest.raises(ValueError, match="batch9"):
        read_questions(pathCsv, "batch9")


def test_the_call_is_the_one_production_makes(retriever, start_openai_server):
    server = start_openai_server(200, completion())
    retriever.openaiclient = client_of(server)
    retriever.llm_draft_model = MODEL
    retriever.process_question({"type": "new", "query": QUESTION["question"]})
    dctPrompt = get_prompt_record(retriever, QUESTION)
    ask_model(client_of(server), MODEL, dctPrompt["prompt"])
    production, harness = server.lstRequests
    assert harness == production
    assert set(harness[1]) == {"model", "messages"}


def test_the_prompt_record_names_the_documents_sent(retriever):
    dctRecord = get_prompt_record(retriever, QUESTION)
    assert dctRecord["question_id"] == "Q01"
    assert dctRecord["question"] == QUESTION["question"]
    assert 5 <= len(dctRecord["ids"]) <= 15
    lstTexts = [retriever.collection.get(ids=[strId])["documents"][0]
                for strId in dctRecord["ids"]]
    assert dctRecord["prompt"].endswith("\n\n".join(lstTexts))


def test_tokens_latency_and_cost_are_recorded(start_openai_server):
    server = start_openai_server(200, completion(dctDetails={"reasoning_tokens": 120}), fDelay=.2)
    dctRecord = ask_model(client_of(server), MODEL, "prompt")
    assert dctRecord["latency"] >= .2
    del dctRecord["latency"]
    fIn, fOut = MODEL_PRICES[MODEL]
    assert dctRecord == {
        "model": MODEL, "model_returned": f"{MODEL}-dated", "answer": "It has four seats.",
        "prompt_tokens": 4000, "completion_tokens": 300, "reasoning_tokens": 120,
        "cost": pytest.approx((4000 * fIn + 300 * fOut) / 1_000_000)}


@pytest.mark.parametrize("dctDetails", [None, {}, {"reasoning_tokens": None}])
def test_reasoning_tokens_are_zero_when_absent(start_openai_server, dctDetails):
    server = start_openai_server(200, completion(dctDetails=dctDetails))
    assert ask_model(client_of(server), MODEL, "prompt")["reasoning_tokens"] == 0


def test_a_model_without_a_price_is_refused_before_it_is_called(start_openai_server):
    server = start_openai_server(200, completion())
    with pytest.raises(ValueError, match="no-such-model"):
        ask_model(client_of(server), "no-such-model", "prompt")
    assert server.lstRequests == []


def test_a_failed_call_is_recorded_with_its_cause_and_no_answer(start_openai_server):
    server = start_openai_server(429, {"error": {"message": "no credits left", "type": None,
                                                 "param": None, "code": "insufficient_quota"}})
    dctRecord = ask_model(client_of(server), MODEL, "prompt")
    assert "answer" not in dctRecord
    assert dctRecord["model"] == MODEL
    assert dctRecord["error"].startswith("RateLimitError")
    assert "no credits left" in dctRecord["error"]


def test_an_unreachable_openai_is_recorded_as_a_failure(unreachable):
    client = openai.OpenAI(api_key="unused", base_url=unreachable, max_retries=0)
    dctRecord = ask_model(client, MODEL, "prompt")
    assert "answer" not in dctRecord
    assert dctRecord["error"].startswith("APIConnectionError")


@pytest.mark.parametrize("strAnswer", [None, "", " \n"])
def test_a_call_that_gives_no_text_is_a_failure_that_keeps_its_tokens(start_openai_server,
                                                                     strAnswer):
    server = start_openai_server(200, completion(strAnswer, strFinish="length"))
    dctRecord = ask_model(client_of(server), MODEL, "prompt")
    assert "answer" not in dctRecord
    assert dctRecord["error"] == "No answer text (finish reason: length)"
    assert dctRecord["completion_tokens"] == 300
    assert dctRecord["cost"] > 0


def test_every_question_is_put_to_every_model_with_the_same_prompt(retriever, start_openai_server,
                                                                   tmp_path, capsys):
    server = start_openai_server(200, completion())
    run_questions(retriever, client_of(server), [QUESTION, OTHER_QUESTION],
                  [MODEL, "gpt-6-luna"], tmp_path)
    lstSent = [(body["model"], body["messages"][0]["content"]) for _, body in server.lstRequests]
    assert [strModel for strModel, _ in lstSent] == [MODEL, "gpt-6-luna"] * 2
    assert lstSent[0][1] == lstSent[1][1] != lstSent[2][1] == lstSent[3][1]
    assert len(retriever.ollamaclient.lstInputs) == 2
    for strId in ("Q01", "Q03"):
        dctPrompt = json.loads((tmp_path / "prompts" / f"{strId}.json").read_text())
        assert dctPrompt["prompt"] in (strPrompt for _, strPrompt in lstSent)
        for strModel in (MODEL, "gpt-6-luna"):
            dctAnswer = json.loads((tmp_path / "answers" / f"{strId}_{strModel}.json").read_text())
            assert dctAnswer["question_id"] == strId
            assert dctAnswer["model"] == strModel
            assert dctAnswer["answer"] == "It has four seats."
    assert capsys.readouterr().out.count("answered") == 4


def test_a_later_model_gets_the_saved_prompt_and_nothing_is_paid_twice(retriever, tmp_path, capsys,
                                                                      start_openai_server):
    server = start_openai_server(200, completion())
    run_questions(retriever, client_of(server), [QUESTION], [MODEL], tmp_path)
    strAnswer = (tmp_path / "answers" / f"Q01_{MODEL}.json").read_text()
    retriever.ollamaclient = None   # a second retrieval would fail
    run_questions(retriever, client_of(server), [QUESTION], [MODEL, "gpt-6-luna"], tmp_path)
    lstBodies = [body for _, body in server.lstRequests]
    assert [body["model"] for body in lstBodies] == [MODEL, "gpt-6-luna"]
    assert lstBodies[0]["messages"] == lstBodies[1]["messages"]
    assert (tmp_path / "answers" / f"Q01_{MODEL}.json").read_text() == strAnswer
    assert "kept" in capsys.readouterr().out


def test_a_failed_call_is_made_again_by_the_next_run(retriever, start_openai_server, tmp_path,
                                                     capsys):
    failing = start_openai_server(500, {"error": {"message": "broken", "code": None}})
    run_questions(retriever, client_of(failing), [QUESTION], [MODEL], tmp_path)
    pathAnswer = tmp_path / "answers" / f"Q01_{MODEL}.json"
    assert "answer" not in json.loads(pathAnswer.read_text())
    assert "FAILED" in capsys.readouterr().out
    run_questions(retriever, client_of(start_openai_server(200, completion())), [QUESTION],
                  [MODEL], tmp_path)
    assert json.loads(pathAnswer.read_text())["answer"] == "It has four seats."
    assert "error" not in json.loads(pathAnswer.read_text())


def test_the_retriever_has_the_settings_of_the_site(collection):
    cfg = configparser.ConfigParser()
    cfg.read_string("[RAG]\nMAX_DISTANCE = .2\nMIN_DOCUMENTS = 3\nMAX_DOCUMENTS = 40\n"
                    "MAX_DRAFT_DOCUMENTS = 7\n[MODELS]\nEMBED = nomic-embed-text\n"
                    "LLM_DRAFT = draft\nLLM_REVISE = revise\n[PROMPTS]\nPREFIX = search_query:\n")
    retriever = create_retriever(cfg, "localhost", "http://localhost:11434")
    assert retriever.max_distance == .2
    assert retriever.min_documents == 3
    assert retriever.max_documents == 40
    assert retriever.max_draft_documents == 7
    assert retriever.embed_prefix == "search_query:"
    assert retriever.collection.name == "nomic-embed-text"
    assert FileProcessorThread.instance is None


def test_only_the_questions_named_are_read(tmp_path):
    pathCsv = tmp_path / "questions.csv"
    pathCsv.write_text("question_id,use,kind,question\nQ01,batch1,factual,one\n"
                       "Q02,batch1,broad,two\nQ03,batch1,broad,three\n")
    lstQuestions = read_questions(pathCsv, "batch1", ["Q03", "Q01"])
    assert [dctQuestion["question_id"] for dctQuestion in lstQuestions] == ["Q01", "Q03"]


def test_a_named_question_that_is_not_in_the_batch_is_refused(tmp_path):
    pathCsv = tmp_path / "questions.csv"
    pathCsv.write_text("question_id,use,kind,question\nQ01,batch1,factual,one\n"
                       "Q02,batch2,broad,two\n")
    with pytest.raises(ValueError, match="Q02"):
        read_questions(pathCsv, "batch1", ["Q01", "Q02"])
