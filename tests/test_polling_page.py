# ABOUTME: Tests what the page that waits for an answer does with each status of its job.
# ABOUTME: Runs the script of the rendered page in node, on real responses of the status route.

import json
import re
import subprocess

import pytest

JOB = {"process_id": "run", "created": 1.0, "elapsed": 2.5, "type": "new", "query": "how many seats"}
RUNNING = dict(JOB, status="start")
FAILED = dict(JOB, status="error")
DONE = dict(JOB, status="complete",
            result={"answer": "It has **four**.", "provided_docs": [], "related_docs": []})

# Loads the page, then calls what it passes to setTimeout until it stops or no answer is left.
# Each element records the properties the page sets on it.
PAGE_RUNNER = """
const vm = require('vm');
const {script, ids, answers} = JSON.parse(require('fs').readFileSync(0, 'utf8'));
const elements = Object.fromEntries(ids.map(id => [id, {}]));
const urls = [];
let next = null;
const page = {
  window: {},
  document: {getElementById: id => elements[id] || null},
  fetch: url => Promise.resolve({json: () => Promise.resolve(answers[urls.push(url) - 1])}),
  setTimeout: callback => { next = callback; },
};
vm.runInNewContext(script, page);
(async () => {
  next = page.window.onload;
  while (next && urls.length < answers.length) {
    const call = next;
    next = null;
    call();
    await new Promise(setImmediate);
  }
  console.log(JSON.stringify({elements, urls, polling: next !== null}));
})();
"""


def status_of(client, pathJobs, dctJob):
    (pathJobs / f"{dctJob['process_id']}.json").write_text(json.dumps(dctJob))
    return client.get(f"/cozyrag/{dctJob['process_id']}/status").get_json()


@pytest.fixture
def poll(client):
    """Runs the page's script on the given answers of the status route."""
    with client.session_transaction() as session:
        session["process_id"] = "run"
    strPage = client.get("/cozyrag/answer").get_data(as_text=True)
    (strScript,) = re.findall(r"<script>(.*?)</script>", strPage, re.DOTALL)
    lstIds = re.findall(r'id="([^"]+)"', strPage)

    def run(*dctAnswers):
        strInput = json.dumps({"script": strScript, "ids": lstIds, "answers": dctAnswers})
        process = subprocess.run(["node", "-e", PAGE_RUNNER], input=strInput, check=True,
                                 capture_output=True, text=True, timeout=20)
        assert process.stderr == ""
        return json.loads(process.stdout)
    return run


def test_a_failed_job_is_shown_and_polling_stops(client, jobs_dir, poll):
    dctStatus = status_of(client, jobs_dir, FAILED)
    assert poll(dctStatus) == {
        "elements": {"result": {"textContent": dctStatus["status_text"]}, "status": {}},
        "urls": ["/cozyrag/run/status"], "polling": False}


def test_the_answer_is_shown_and_polling_stops(client, jobs_dir, poll):
    dctStatus = status_of(client, jobs_dir, DONE)
    assert "<strong>four</strong>" in dctStatus["result_html"]
    assert poll(dctStatus) == {
        "elements": {"result": {"innerHTML": dctStatus["result_html"]}, "status": {}},
        "urls": ["/cozyrag/run/status"], "polling": False}


def test_a_running_job_shows_its_status_and_polling_goes_on(client, jobs_dir, poll):
    dctStatus = status_of(client, jobs_dir, RUNNING)
    assert poll(dctStatus) == {
        "elements": {"result": {}, "status": {"textContent": dctStatus["status_text"]}},
        "urls": ["/cozyrag/run/status"], "polling": True}


@pytest.mark.parametrize("dctJob, strProperty", [(FAILED, "textContent"), (DONE, "innerHTML")])
def test_polling_goes_on_until_the_job_ends(client, jobs_dir, poll, dctJob, strProperty):
    dctRunning = status_of(client, jobs_dir, RUNNING)
    dctEnd = status_of(client, jobs_dir, dctJob)
    dctPage = poll(dctRunning, dctRunning, dctEnd, dctRunning)
    assert dctPage["urls"] == ["/cozyrag/run/status"] * 3
    assert strProperty in dctPage["elements"]["result"]
    assert not dctPage["polling"]
