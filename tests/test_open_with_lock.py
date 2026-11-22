# ABOUTME: Tests that a job file being rewritten is never seen empty by a reader.
# ABOUTME: Uses real files and real locks; a writer's wait for the lock is observed.

import fcntl
import json
import os
import threading
import time
from types import SimpleNamespace

import pytest

import src.open_with_lock
from src.open_with_lock import open_with_lock
from src.site_functions import update_process_info

TIMEOUT = 10
BEFORE = {"status": "start", "query": "how many seats"}


@pytest.fixture
def job_file(tmp_path):
    pathJob = tmp_path / "abc.json"
    pathJob.write_text(json.dumps(BEFORE))
    return pathJob


@pytest.fixture
def writer_waiting(monkeypatch):
    """Set each time a writer finds the file locked and is about to try again."""
    eventWaiting = threading.Event()

    def sleep(fSeconds):
        eventWaiting.set()
        time.sleep(fSeconds)

    monkeypatch.setattr(src.open_with_lock, "time", SimpleNamespace(sleep=sleep))
    return eventWaiting


def open_descriptors():
    return sorted(os.listdir("/proc/self/fd"))


def test_file_keeps_its_content_until_the_writer_has_the_lock(job_file, writer_waiting, capsys):
    threadWriter = threading.Thread(
        target=update_process_info,
        args=({"status": "complete"}, str(job_file.parent)), kwargs={"filename": job_file.name})
    with open(job_file) as fileReader:
        fcntl.flock(fileReader, fcntl.LOCK_SH)
        threadWriter.start()
        assert writer_waiting.wait(TIMEOUT)
        assert json.loads(job_file.read_text()) == BEFORE
    threadWriter.join(TIMEOUT)

    assert not threadWriter.is_alive()
    assert json.loads(job_file.read_text())["status"] == "complete"
    assert f"File {job_file} is currently locked. Retrying 1/50..." in capsys.readouterr().out


def test_shorter_content_replaces_longer_content(job_file):
    with open_with_lock(str(job_file), "w") as f:
        f.write("{}")
    assert job_file.read_text() == "{}"


def test_retries_leave_no_descriptor_open(job_file, capsys):
    with open(job_file) as fileReader:
        fcntl.flock(fileReader, fcntl.LOCK_SH)
        lstBefore = open_descriptors()
        with pytest.raises(OSError, match="Could not acquire lock"):
            open_with_lock(str(job_file), "w", max_retries=3, wait_secs=0)
        assert open_descriptors() == lstBefore
    assert json.loads(job_file.read_text()) == BEFORE
    assert capsys.readouterr().out.splitlines() == [
        f"File {job_file} is currently locked. Retrying {i}/3..." for i in (1, 2, 3)]
