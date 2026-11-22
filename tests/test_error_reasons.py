# ABOUTME: Tests that a failed OpenAI call ends a job in error, and which reason the visitor is shown.
# ABOUTME: The real OpenAI client calls a local server that answers with each failure.

import json
import threading
import time
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

import openai
import pytest

from job_loop import run_jobs

REVISE = {"process_id": "job", "status": "revise", "created": 1.0, "query": "how many seats",
          "result": {"answer": "It has four seats.", "related_docs": [],
                     "provided_docs": [{"id": "ttXB7VHdy1w0"}]}}
FOLLOWUP = dict(REVISE, status="followup", query="and how many doors")
DETAIL = "detail of the account"
GENERIC = ("The question could not be answered. Please try again in a few minutes. "
           "If it keeps failing, please let Tom know.")


def let_tom_know(strPhrase):
    return ("The site cannot answer questions until Tom fixes it. Please let him know: "
            f"{strPhrase}.")


@pytest.fixture
def openai_answers(processor):
    """Makes the processor's OpenAI client call a server that gives the answer passed in."""
    lstServers = []

    def start(intStatus, strCode=None, strType=None, fDelay=0):
        class Handler(BaseHTTPRequestHandler):
            def do_POST(self):
                self.rfile.read(int(self.headers["Content-Length"]))
                time.sleep(fDelay)
                binBody = json.dumps({"error": {"message": DETAIL, "type": strType, "param": None,
                                                "code": strCode}}).encode()
                self.send_response(intStatus)
                self.send_header("Content-Type", "application/json")
                self.send_header("Content-Length", str(len(binBody)))
                self.end_headers()
                self.wfile.write(binBody)

            def log_message(self, *args):
                pass

        server = ThreadingHTTPServer(("127.0.0.1", 0), Handler)
        lstServers.append(server)
        threading.Thread(target=server.serve_forever, daemon=True).start()
        use_openai_at(processor, f"http://127.0.0.1:{server.server_port}")
    yield start
    for server in lstServers:
        server.shutdown()
        server.server_close()


def use_openai_at(processor, strUrl):
    processor.openaiclient = openai.OpenAI(api_key="unused", base_url=strUrl, max_retries=0,
                                           timeout=5)


@pytest.fixture
def failed(processor, client, jobs_dir, capsys):
    """Runs one job that fails. Gives its record, what was logged and its status response."""
    def run(dctJob=REVISE):
        run_jobs(processor, jobs_dir, [dctJob])
        strRecord = (jobs_dir / "job.json").read_text()
        dctStatus = client.get("/cozyrag/job/status").get_json()
        strOut = capsys.readouterr().out
        assert "job.json: Job failed." in strOut
        assert "Traceback (most recent call last):" in strOut
        assert DETAIL not in strRecord + json.dumps(dctStatus)
        assert dctStatus["status"] == "error"
        return json.loads(strRecord), strOut, dctStatus["status_text"]
    return run


@pytest.mark.parametrize("intStatus, strCode, strReason, strPhrase", [
    (401, "invalid_api_key", "openai_access", "OpenAI key rejected"),
    (403, None, "openai_access", "OpenAI key rejected"),
    (404, "model_not_found", "openai_model", "OpenAI model not available")])
def test_the_visitor_is_shown_what_tom_has_to_fix(openai_answers, failed, intStatus, strCode,
                                                  strReason, strPhrase):
    openai_answers(intStatus, strCode)
    dctJob, strOut, strText = failed()
    assert dctJob["error_reason"] == strReason
    assert DETAIL in strOut
    assert strText == let_tom_know(strPhrase)


@pytest.mark.parametrize("strCode, strType", [
    ("credit_balance_exhausted", None), ("organization_spend_limit_exceeded", None),
    ("project_spend_limit_exceeded", None), ("organization_usage_limit_exceeded", None),
    ("insufficient_quota", None), ("insufficient_quota", "insufficient_quota"),
    (None, "insufficient_quota"), ("another_code", "insufficient_quota")])
def test_the_visitor_is_shown_that_the_budget_is_used_up(openai_answers, failed, strCode, strType):
    openai_answers(429, strCode, strType)
    dctJob, strOut, strText = failed()
    assert dctJob["error_reason"] == "openai_budget"
    assert DETAIL in strOut
    assert strText == let_tom_know("OpenAI budget used up")


@pytest.mark.parametrize("intStatus, strCode, strType", [
    (429, "rate_limit_exceeded", "requests"), (429, "slow_down", "rate_limit_error"),
    (429, None, None), (400, "insufficient_quota", "insufficient_quota"),
    (500, None, None), (503, None, None)])
def test_other_failures_have_no_reason(openai_answers, failed, intStatus, strCode, strType):
    openai_answers(intStatus, strCode, strType)
    dctJob, strOut, strText = failed()
    assert "error_reason" not in dctJob
    assert DETAIL in strOut
    assert strText == GENERIC


def test_openai_unreachable_has_no_reason(processor, unreachable, failed):
    use_openai_at(processor, unreachable)
    dctJob, strOut, strText = failed()
    assert "error_reason" not in dctJob
    assert "APIConnectionError" in strOut
    assert strText == GENERIC


def test_openai_timeout_has_no_reason(processor, openai_answers, failed):
    openai_answers(200, fDelay=1)
    processor.openaiclient = processor.openaiclient.with_options(timeout=.2)
    dctJob, strOut, strText = failed()
    assert "error_reason" not in dctJob
    assert "APITimeoutError" in strOut
    assert strText == GENERIC


def test_a_failure_without_a_reason_clears_an_earlier_one(openai_answers, failed):
    openai_answers(500)
    dctJob, _, strText = failed(REVISE | {"error_reason": "openai_access"})
    assert "error_reason" not in dctJob
    assert strText == GENERIC


def test_a_failed_revise_keeps_its_draft(openai_answers, failed):
    openai_answers(401)
    dctJob, _, _ = failed()
    assert {key: dctJob[key] for key in REVISE} == dict(REVISE, status="error")


def test_a_failed_followup_keeps_the_answer_it_follows(processor, openai_answers, failed,
                                                       monkeypatch, collection):
    rQuery = collection.query(query_embeddings=collection.get(limit=1, include=["embeddings"])
                              ["embeddings"], n_results=60)
    monkeypatch.setattr(processor, "get_query_results", lambda strQuestion: rQuery)
    openai_answers(401)
    dctJob, _, _ = failed(FOLLOWUP)
    assert {key: dctJob[key] for key in FOLLOWUP} == dict(FOLLOWUP, status="error")
