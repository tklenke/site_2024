# ABOUTME: Fixtures shared by the tests of the job processing code.
# ABOUTME: Gives a job processor on the real collection that records the prompts it sends.

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
