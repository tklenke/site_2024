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


def set_session(client, **dctValues):
    with client.session_transaction() as session:
        session.update(dctValues)


# ---- revise
def test_revise_accepts_post_only(client, jobs_dir):
    write_job(jobs_dir, DONE)
    set_session(client, process_id="done")
    assert client.get("/cozyrag/revise").status_code == 405
    assert len(list(jobs_dir.iterdir())) == 1


def test_revise_creates_a_revise_job(client, jobs_dir):
    write_job(jobs_dir, DONE)
    set_session(client, process_id="done")
    response = client.post("/cozyrag/revise")
    assert response.location == "/cozyrag/answer"
    with client.session_transaction() as session:
        strId = session["process_id"]
    assert strId != "done"
    assert read_job(jobs_dir, strId)["status"] == "revise"


# ---- requests without a session
@pytest.mark.parametrize("dctSession", [{}, {"process_id": None}])
@pytest.mark.parametrize("strMethod, strPath", [
    ("post", "/cozyrag/revise"), ("get", "/cozyrag/followup"), ("post", "/cozyrag/followup"),
    ("post", "/cozyrag/feedback"), ("get", "/cozyrag/answer")])
def test_without_a_session_redirects_to_the_question_form(client, jobs_dir, strMethod, strPath,
                                                          dctSession):
    set_session(client, **dctSession)
    response = client.open(strPath, method=strMethod,
                           data={"question": "what engine", "satisfaction": "ok"}
                           if strMethod == "post" else None)
    assert response.status_code == 302
    assert response.location == "/cozyrag/query"
    assert list(jobs_dir.iterdir()) == []


# ---- revising or following up a job that has no answer
@pytest.mark.parametrize("lstJobs, strId", [([RUNNING], "run"), ([], "nosuchjob")])
@pytest.mark.parametrize("strPath", ["/cozyrag/revise", "/cozyrag/followup"])
def test_job_without_an_answer_redirects_to_the_question_form(client, jobs_dir, capsys, strPath,
                                                              lstJobs, strId):
    for dctJob in lstJobs:
        write_job(jobs_dir, dctJob)
    set_session(client, process_id=strId)
    response = client.post(strPath, data={"question": "what engine"})
    assert response.location == "/cozyrag/query"
    assert len(list(jobs_dir.iterdir())) == len(lstJobs)
    assert (f"{strId}.json" in capsys.readouterr().out) == (strId == "nosuchjob")


# ---- unknown jobs and columns
@pytest.mark.parametrize("strPage", ["status", "processid"])
def test_unknown_job_is_not_found(client, capsys, strPage):
    assert client.get(f"/cozyrag/nosuchjob/{strPage}").status_code == 404
    assert "nosuchjob.json" in capsys.readouterr().out


def test_results_of_an_unfinished_job_are_not_found(client, jobs_dir):
    write_job(jobs_dir, RUNNING)
    assert client.get("/cozyrag/run/processid").status_code == 404


def test_unknown_column_is_not_found(client, jobs_dir):
    assert client.get("/cozyrag/jobs/nosuchcolumn").status_code == 404


# ---- a failed job
@pytest.mark.parametrize("dctJob", [dict(RUNNING, status="error"),
                                    dict(DONE, process_id="run", status="error")])
def test_status_of_a_failed_job_tells_the_visitor(client, jobs_dir, dctJob):
    write_job(jobs_dir, dctJob)
    assert client.get("/cozyrag/run/status").get_json() == {
        "status": "error",
        "status_text": "Your question could not be answered. Please try again."}


# ---- feedback
@pytest.mark.parametrize("strRating", ["perfect", "ok", "not_good"])
def test_feedback_is_recorded(client, jobs_dir, strRating):
    write_job(jobs_dir, DONE)
    set_session(client, process_id="done")
    response = client.post("/cozyrag/feedback", data={"satisfaction": strRating})
    assert response.location == "/cozyrag/query"
    assert read_job(jobs_dir, "done")["satisfaction"] == strRating


@pytest.mark.parametrize("dctForm", [{"satisfaction": "n/a"}, {"satisfaction": ""}, {}])
def test_other_feedback_is_ignored(client, jobs_dir, dctForm):
    write_job(jobs_dir, DONE)
    set_session(client, process_id="done")
    response = client.post("/cozyrag/feedback", data=dctForm)
    assert response.location == "/cozyrag/query"
    assert read_job(jobs_dir, "done") == DONE
    with client.session_transaction() as session:
        assert "_flashes" not in session


# ---- asking a question
def test_question_creates_one_job(client, jobs_dir):
    response = client.post("/cozyrag/query", data={"question": "what engine",
                                                   "email": "a@example.com"})
    assert response.location == "/cozyrag/answer"
    with client.session_transaction() as session:
        dctJob = read_job(jobs_dir, session["process_id"])
    assert dctJob["status"] == "new"
    assert dctJob["query"] == "what engine"
    assert dctJob["email"] == "a@example.com"
    assert len(list(jobs_dir.iterdir())) == 1


def test_question_is_queued(client, site_app, jobs_dir):
    while not site_app.FPQueue.empty():
        site_app.FPQueue.get()
    client.post("/cozyrag/query", data={"question": "what engine"})
    with client.session_transaction() as session:
        assert site_app.FPQueue.get_nowait() == session["process_id"]
    assert site_app.FPQueue.empty()


def test_address_is_remembered_for_the_next_question(client, jobs_dir):
    client.post("/cozyrag/query", data={"question": "what engine", "email": "a@example.com"})
    client.post("/cozyrag/query", data={"question": "what canopy"})
    with client.session_transaction() as session:
        assert read_job(jobs_dir, session["process_id"])["email"] == "a@example.com"


def test_answer_page_polls_the_job(client, jobs_dir):
    client.post("/cozyrag/query", data={"question": "what engine"})
    with client.session_transaction() as session:
        strId = session["process_id"]
    assert f"/cozyrag/{strId}/status" in client.get("/cozyrag/answer").get_data(as_text=True)


def test_reading_pages_creates_no_job(client, jobs_dir):
    client.post("/cozyrag/query", data={"question": "what engine"})
    for _ in range(3):
        client.get("/cozyrag/answer")
        client.get("/cozyrag/query")
        response = client.get("/cozyrag/answer")
    assert response.location == "/cozyrag/query"
    assert len(list(jobs_dir.iterdir())) == 1


# ---- user input
HTML = "<b>seats</b> & <script>alert(1)</script>"


def test_question_and_address_are_kept_as_plain_text(client, jobs_dir):
    response = client.post("/cozyrag/query", data={"question": HTML, "email": "a@example.com"})
    assert response.location == "/cozyrag/answer"
    with client.session_transaction() as session:
        assert type(session["email"]) is str
        strId = session["process_id"]
    assert read_job(jobs_dir, strId)["query"] == HTML


def test_followup_question_is_recorded_as_typed(client, jobs_dir):
    write_job(jobs_dir, DONE)
    set_session(client, process_id="done")
    client.post("/cozyrag/followup", data={"question": HTML})
    with client.session_transaction() as session:
        strId = session["process_id"]
    assert read_job(jobs_dir, strId)["query"] == HTML


@pytest.mark.parametrize("strPath", ["/cozyrag/done/processid", "/cozyrag/jobs",
                                     "/cozyrag/jobs/query"])
def test_question_is_escaped_on_the_page(client, jobs_dir, strPath):
    write_job(jobs_dir, dict(DONE, query=HTML))
    strPage = client.get(strPath).get_data(as_text=True)
    assert "<script>alert" not in strPage
    assert "&lt;script&gt;alert" in strPage


@pytest.mark.parametrize("strPath", ["/cozyrag/query", "/cozyrag/followup"])
@pytest.mark.parametrize("dctForm", [{}, {"question": ""}])
def test_question_is_required(client, jobs_dir, strPath, dctForm):
    set_session(client, process_id="done")
    response = client.post(strPath, data=dctForm)
    assert response.status_code == 200
    assert "Question is required." in response.get_data(as_text=True)
    assert list(jobs_dir.iterdir()) == []
