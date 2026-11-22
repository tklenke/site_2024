# ABOUTME: Runs the loop of the job thread on given jobs, for the tests of job processing.
# ABOUTME: The jobs are real files, written when the loop asks for them.

import json

import pytest


class EndOfJobs(Exception):
    """Raised when the loop asks for a job after the last one."""


class JobQueue:
    """Gives the loop the jobs in turn. A job's file is written when the loop asks for the job."""

    def __init__(self, pathJobs, lstJobs):
        self.pathJobs = pathJobs
        self.lstJobs = list(lstJobs)

    def get(self):
        if not self.lstJobs:
            raise EndOfJobs
        job = self.lstJobs.pop(0)
        if isinstance(job, dict):
            (self.pathJobs / f"{job['process_id']}.json").write_text(json.dumps(job))
        else:
            strName, strContent = job
            (self.pathJobs / strName).write_text(strContent)
        return job

    def task_done(self):
        pass


def run_jobs(processor, pathJobs, lstJobs):
    """Runs the job loop until it asks for a job after the last one."""
    processor.job_path = str(pathJobs)
    processor.job_queue = JobQueue(pathJobs, lstJobs)
    with pytest.raises(EndOfJobs):
        processor.run()
