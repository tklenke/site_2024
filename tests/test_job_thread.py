# ABOUTME: Tests that a job that fails is marked as failed and that the job loop goes on.
# ABOUTME: Failures come from real unreachable services and real malformed job files.

import json

import ollama
import pytest

from job_loop import run_jobs
from src.site_functions import update_process_status

PROVIDED = ["cb__ref_info_-_kitplane___html101", "ttXB7VHdy1w0"]
ANSWERED = {"answer": "It has four seats.", "related_docs": [],
            "provided_docs": [{"id": strId} for strId in PROVIDED]}
NEW = {"process_id": "new", "status": "new", "created": 1.0, "query": "what engine fits"}
REVISE = {"process_id": "revise", "status": "revise", "created": 1.0, "query": "how many seats",
          "email": "a@example.com", "result": ANSWERED}
FOLLOWUP = dict(REVISE, process_id="followup", status="followup", query="and how many doors")
NO_QUERY = {"process_id": "noquery", "status": "new", "created": 1.0}


def read_job(pathJobs, strId):
    return json.loads((pathJobs / f"{strId}.json").read_text())


@pytest.fixture
def without_ollama(processor, unreachable):
    processor.ollamaclient = ollama.Client(unreachable)
    processor.embed_model = "nomic-embed-text"
    processor.set_embed_prefix("search_query:")


@pytest.fixture
def without_chroma(processor, unreachable, monkeypatch):
    monkeypatch.setattr(processor.collection._client, "_api_url", f"{unreachable}/api/v2")


# ---- a service that cannot be reached
@pytest.mark.parametrize("dctJob", [NEW, FOLLOWUP])
def test_job_is_marked_failed_when_ollama_is_unreachable(processor, without_ollama, tmp_path,
                                                         capsys, dctJob):
    run_jobs(processor, tmp_path, [dctJob])
    assert read_job(tmp_path, dctJob["process_id"])["status"] == "error"
    strOut = capsys.readouterr().out
    assert f"{dctJob['process_id']}.json: Job failed." in strOut
    assert "Traceback (most recent call last):" in strOut
    assert "Failed to connect to Ollama" in strOut


def test_job_is_marked_failed_when_chroma_is_unreachable(processor, without_chroma, tmp_path,
                                                         capsys):
    run_jobs(processor, tmp_path, [REVISE])
    assert read_job(tmp_path, "revise")["status"] == "error"
    strOut = capsys.readouterr().out
    assert "revise.json: Job failed." in strOut
    assert "Traceback (most recent call last):" in strOut
    assert "Connection refused" in strOut


def test_the_next_job_is_answered_after_a_failure(processor, without_ollama, tmp_path, capsys):
    run_jobs(processor, tmp_path, [NEW, REVISE])
    assert read_job(tmp_path, "new")["status"] == "error"
    dctRevise = read_job(tmp_path, "revise")
    assert dctRevise["status"] == "complete"
    assert dctRevise["result"]["answer"] == "ok"
    assert capsys.readouterr().out.count("Job failed.") == 1


def test_a_failed_job_is_not_tried_again(processor, without_ollama, tmp_path, capsys):
    run_jobs(processor, tmp_path, [NEW, REVISE, FOLLOWUP | {"status": "complete"}])
    strOut = capsys.readouterr().out
    assert strOut.count("new.json: Job failed.") == 1
    assert read_job(tmp_path, "new")["status"] == "error"


def test_a_failed_revise_keeps_the_rest_of_its_record(processor, without_chroma, tmp_path, capsys):
    run_jobs(processor, tmp_path, [REVISE])
    dctJob = read_job(tmp_path, "revise")
    assert {key: dctJob[key] for key in REVISE} == dict(REVISE, status="error")
    assert "Job failed." in capsys.readouterr().out


# ---- job files that cannot be used
@pytest.mark.parametrize("strContent", ["not json", "", "[]", "\udcff"])
def test_an_unreadable_job_is_logged_and_left_as_it_is(processor, tmp_path, capsys, strContent):
    binContent = strContent.encode("utf-8", "surrogateescape")
    pathJob = tmp_path / "bad.json"
    pathJob.write_bytes(binContent)
    run_jobs(processor, tmp_path, [REVISE])
    assert pathJob.read_bytes() == binContent
    assert read_job(tmp_path, "revise")["status"] == "complete"
    strOut = capsys.readouterr().out
    assert strOut.count("bad.json: Job failed.") == 1
    assert strOut.count("bad.json: Could not set the status to error.") == 1


def test_an_unreadable_job_is_not_looked_at_again(processor, tmp_path, capsys):
    run_jobs(processor, tmp_path, [("bad.json", "not json"), REVISE, FOLLOWUP | {"status": "complete"}])
    assert read_job(tmp_path, "revise")["status"] == "complete"
    assert capsys.readouterr().out.count("bad.json: Job failed.") == 1


def test_a_job_without_a_status_is_marked_failed(processor, tmp_path, capsys):
    run_jobs(processor, tmp_path, [{"process_id": "odd", "created": 1.0, "query": "what engine"}])
    assert read_job(tmp_path, "odd")["status"] == "error"
    assert "odd.json: Job failed." in capsys.readouterr().out


def test_a_job_without_a_question_is_marked_failed(processor, tmp_path, capsys):
    run_jobs(processor, tmp_path, [NO_QUERY, REVISE])
    assert read_job(tmp_path, "noquery")["status"] == "error"
    assert read_job(tmp_path, "revise")["status"] == "complete"
    strOut = capsys.readouterr().out
    assert "noquery.json: Missing 'query' key or null value in JSON data." in strOut
    assert "Job failed." not in strOut


def test_the_status_of_an_unreadable_job_is_not_set(tmp_path, capsys):
    pathJob = tmp_path / "bad.json"
    pathJob.write_text("not json")
    with pytest.raises(ValueError, match="bad.json"):
        update_process_status("error", str(tmp_path), filename="bad.json")
    assert pathJob.read_text() == "not json"
    assert "Error decoding JSON file: bad.json" in capsys.readouterr().out


@pytest.mark.parametrize("dctReason, strExpected", [({}, None), ({"error_reason": "b"}, "b")])
def test_a_status_is_saved_with_its_own_reason_only(tmp_path, dctReason, strExpected):
    (tmp_path / "job.json").write_text(json.dumps(REVISE | {"error_reason": "a"}))
    update_process_status("error", str(tmp_path), filename="job.json", **dctReason)
    assert read_job(tmp_path, "job").get("error_reason") == strExpected
