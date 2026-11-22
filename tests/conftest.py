# ABOUTME: Fixtures shared by the tests of the job processing code and of the site's pages.
# ABOUTME: Gives a processor on the real collection, and the Flask app with real job files.

import os
import socket
from types import SimpleNamespace

import chromadb
import pytest

import src.llm_functions
from src.llm_functions import FileProcessorThread

COLLECTION = "nomic-embed-text"
SITE_INI = """
[LEVEL]
DEBUG = False
[PATHS]
JOBS_DIR = unset
WWW_DIR = unset
[RAG]
USE_GPT = False
MAX_QUERY_LEN = 1024
MAX_INPUT_LEN = 75
PROCESS_ID_LEN = 10
MAX_DISTANCE = .35
MIN_DOCUMENTS = 5
MAX_DOCUMENTS = 60
MAX_DRAFT_DOCUMENTS = 15
[HOSTS]
OLLAMA = unused
CHROMA = unused
[MODELS]
EMBED = unused
LLM_DRAFT = unused
LLM_REVISE = unused
[PROMPTS]
PREFIX = search_query:
[OPTIONS]
SHOW_REVISE = True
"""


class NoJobThread:
    """Stands in for the job thread, which connects to the services when it is created."""

    def __init__(self, *args):
        pass

    def set_models(self, *args):
        pass

    def set_embed_prefix(self, *args):
        pass

    def set_docs_params(self, *args):
        pass


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
    processor.llm_draft_model = "draft-model"
    processor.llm_revise_model = "revise-model"
    processor.set_docs_params(max_distance=.35, min_documents=5, max_documents=60,
                              max_draft_documents=15)
    processor.lstPrompts = []

    def create(model, messages):
        processor.lstPrompts.append(messages[0]["content"])
        return SimpleNamespace(choices=[SimpleNamespace(message=SimpleNamespace(content="ok"))],
                               model=model,
                               usage=SimpleNamespace(prompt_tokens=1, completion_tokens=1))

    processor.openaiclient = SimpleNamespace(
        chat=SimpleNamespace(completions=SimpleNamespace(create=create)))
    return processor


@pytest.fixture(scope="session")
def site_app(tmp_path_factory):
    """The site's app module. Its job thread is left out, so no service is needed."""
    pathRun = tmp_path_factory.mktemp("run")
    (pathRun / "site.ini").write_text(SITE_INI)
    (pathRun / "site_local.ini").write_text("[KEYS]\nSESSION = session-key\nOPENAI = unused\n")
    strCwd = os.getcwd()
    with pytest.MonkeyPatch.context() as patch:
        patch.setattr(src.llm_functions, "FileProcessorThread", NoJobThread)
        os.chdir(pathRun)
        try:
            import site_app
        finally:
            os.chdir(strCwd)
    return site_app


@pytest.fixture
def jobs_dir(site_app, tmp_path):
    """An empty job directory that the app uses."""
    pathJobs = tmp_path / "jobs"
    pathJobs.mkdir()
    site_app.cfg.set("PATHS", "JOBS_DIR", str(pathJobs))
    return pathJobs


@pytest.fixture
def client(site_app, jobs_dir):
    return site_app.app.test_client()


@pytest.fixture
def unreachable():
    """An address at which nothing listens."""
    with socket.socket() as sock:
        sock.bind(("127.0.0.1", 0))
        return f"http://127.0.0.1:{sock.getsockname()[1]}"
