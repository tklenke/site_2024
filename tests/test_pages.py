# ABOUTME: Tests the site's CozyRAG routes through Flask's test client.
# ABOUTME: Job files are real files in a temporary directory.

import json

import pytest

DONE = {"process_id": "done", "status": "complete", "created": 1.0, "elapsed": 2.5, "type": "new",
        "query": "how many seats",
        "result": {"answer": "Four.", "provided_docs": [], "related_docs": []}}
RUNNING = {"process_id": "run", "status": "start", "created": 2.0, "query": "what engine fits"}
COLUMNS = ["email", "tokens_in", "tokens_out", "elapsed", "num_docs", "avg_score",
           "satisfaction", "query", "answer"]


def write_job(pathJobs, dctJob):
    (pathJobs / f"{dctJob['process_id']}.json").write_text(json.dumps(dctJob))


def read_job(pathJobs, strId):
    return json.loads((pathJobs / f"{strId}.json").read_text())


@pytest.mark.parametrize("strPath", ["/cozyrag/jobs"] + [f"/cozyrag/jobs/{c}" for c in COLUMNS])
def test_jobs_page_shows_an_unfinished_job(client, jobs_dir, strPath):
    write_job(jobs_dir, DONE)
    write_job(jobs_dir, RUNNING)
    assert client.get(strPath).status_code == 200


def test_jobs_page_lists_the_question_of_an_unfinished_job(client, jobs_dir):
    write_job(jobs_dir, RUNNING)
    assert "what engine fits" in client.get("/cozyrag/jobs").get_data(as_text=True)
