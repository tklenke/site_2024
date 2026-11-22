# ABOUTME: Tests that a full email address is never sent to a web page.
# ABOUTME: Uses a real job file holding a known address and reads whole responses.

import json
import re
import time

import pytest

from src.site_functions import shorten_email

EMAIL = "someone.private@example.com"
JOB = {"process_id": "abc", "status": "complete", "created": 1.0, "elapsed": 2.5,
       "query": "how many seats", "email": EMAIL, "type": "new",
       "result": {"answer": "Four.", "model": "model-a", "time": 1.0, "type": "new",
                  "prompt tokens": 10, "completion tokens": 5, "number provided docs": 1,
                  "average score": "0.70", "related_docs": [],
                  "provided_docs": [{"id": "x0", "score": "0.70",
                                     "source": "./data/news/news_78.txt"}]}}


@pytest.fixture
def job(jobs_dir):
    (jobs_dir / "abc.json").write_text(json.dumps(JOB))


@pytest.mark.parametrize("strEmail, strShort", [
    (EMAIL, "someo..."), ("", ""), (None, ""), ("ab", "ab..."), ("abcde", "abcde...")])
def test_shorten_email(strEmail, strShort):
    assert shorten_email(strEmail) == strShort


@pytest.mark.parametrize("strPath", [
    "/cozyrag/abc/status", "/cozyrag/abc/processid", "/cozyrag/jobs", "/cozyrag/jobs/email",
    "/cozyrag/jobs/query"])
def test_full_address_is_in_no_response(client, job, strPath):
    response = client.get(strPath)
    assert response.status_code == 200
    assert EMAIL not in response.get_data(as_text=True)


@pytest.mark.parametrize("strPath", [
    "/cozyrag/abc/status", "/cozyrag/abc/processid", "/cozyrag/jobs", "/cozyrag/jobs/email"])
def test_shortened_address_is_shown(client, job, strPath):
    assert "someo..." in client.get(strPath).get_data(as_text=True)


def test_status_of_complete_job_has_only_what_the_page_reads(client, job):
    assert set(client.get("/cozyrag/abc/status").get_json()) == {"status", "result_html"}


# the status text ends in a dot for each second since a multiple of ten: 100 seconds give none
@pytest.mark.parametrize("fAge", [100.2, 103.2])
def test_status_of_running_job_has_only_what_the_page_reads(client, jobs_dir, fAge):
    dctJob = {"process_id": "run", "status": "start", "created": time.time() - fAge, "query": "q",
              "email": EMAIL}
    (jobs_dir / "run.json").write_text(json.dumps(dctJob))
    dctStatus = client.get("/cozyrag/run/status").get_json()
    assert set(dctStatus) == {"status", "status_text"}
    assert re.fullmatch(r"Status: start\.{0,9}", dctStatus["status_text"])


def test_jobs_page_lists_a_job_without_an_address(client, jobs_dir):
    dctJob = {key: JOB[key] for key in JOB if key != "email"}
    (jobs_dir / "abc.json").write_text(json.dumps(dctJob))
    for strPath in ("/cozyrag/jobs", "/cozyrag/jobs/email", "/cozyrag/abc/processid"):
        assert client.get(strPath).status_code == 200


def test_job_file_keeps_the_full_address(client, job, jobs_dir):
    client.get("/cozyrag/jobs")
    client.get("/cozyrag/abc/status")
    client.get("/cozyrag/abc/processid")
    assert json.loads((jobs_dir / "abc.json").read_text())["email"] == EMAIL
