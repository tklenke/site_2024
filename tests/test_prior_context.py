# ABOUTME: Tests that revise and follow-up prompts carry the full text of every prior document.
# ABOUTME: Reads real documents from the local Chroma service; only the model call is recorded.

from types import SimpleNamespace

import chromadb
import pytest

from src.llm_functions import FileProcessorThread

COLLECTION = "nomic-embed-text"


@pytest.fixture(scope="module")
def collection():
    try:
        return chromadb.HttpClient(host="localhost").get_collection(COLLECTION)
    except Exception as e:
        pytest.fail(f"Needs the local Chroma service (docker compose up -d chroma-rag): {e}")


@pytest.fixture
def processor(collection):
    """A job processor on the real collection, without its thread. Prompts sent are recorded."""
    processor = FileProcessorThread.__new__(FileProcessorThread)
    processor.collection = collection
    processor.use_gpt = True
    processor.llm_revise_model = "revise-model"
    processor.lstPrompts = []

    def create(model, messages):
        processor.lstPrompts.append(messages[0]["content"])
        return SimpleNamespace(choices=[SimpleNamespace(message=SimpleNamespace(content="ok"))],
                               model=model,
                               usage=SimpleNamespace(prompt_tokens=1, completion_tokens=1))

    processor.openaiclient = SimpleNamespace(
        chat=SimpleNamespace(completions=SimpleNamespace(create=create)))
    return processor


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
