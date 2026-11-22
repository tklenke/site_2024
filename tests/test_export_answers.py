# ABOUTME: Tests the export of one model's saved answers to markdown files.
# ABOUTME: Checks what a file holds and that a kept answer is never replaced by another one.

import pytest

from answer_models import write_json
from export_answers import export_answers

MODEL = "gpt-4o-mini"
QUESTION = {"question_id": "Q01", "kind": "factual", "question": "how many seats"}
ANSWER = {"question_id": "Q01", "model": MODEL, "latency": 4.4538, "model_returned": f"{MODEL}-dated",
          "prompt_tokens": 4511, "completion_tokens": 125, "reasoning_tokens": 0,
          "cost": 0.00075165, "answer": "It has **four**.\n\n- two\n- two"}
EXPECTED = """# Q01: how many seats

- Kind: factual
- Model: gpt-4o-mini-dated
- Prompt tokens: 4511
- Completion tokens: 125
- Reasoning tokens: 0
- Latency: 4.5 s
- Cost: $0.00075
- Documents: idA, idB

## Answer

It has **four**.

- two
- two
"""


def save(pathOutput, dctAnswer=ANSWER):
    write_json(str(pathOutput / "prompts" / "Q01.json"),
               QUESTION | {"ids": ["idA", "idB"], "prompt": "text from someone@example.com"})
    write_json(str(pathOutput / "answers" / f"Q01_{MODEL}.json"), dctAnswer)


@pytest.fixture
def archive(tmp_path):
    return tmp_path / "archive"


def test_the_file_holds_the_answer_and_its_figures_but_not_the_prompt(tmp_path, archive):
    save(tmp_path)
    export_answers(str(tmp_path), [QUESTION], MODEL, str(archive))
    assert [path.name for path in archive.iterdir()] == ["Q01.md"]
    assert (archive / "Q01.md").read_text() == EXPECTED


def test_exporting_again_changes_nothing(tmp_path, archive):
    save(tmp_path)
    export_answers(str(tmp_path), [QUESTION], MODEL, str(archive))
    export_answers(str(tmp_path), [QUESTION], MODEL, str(archive))
    assert (archive / "Q01.md").read_text() == EXPECTED


def test_a_kept_answer_is_not_replaced(tmp_path, archive):
    save(tmp_path)
    export_answers(str(tmp_path), [QUESTION], MODEL, str(archive))
    save(tmp_path, ANSWER | {"answer": "another"})
    with pytest.raises(ValueError, match="Q01"):
        export_answers(str(tmp_path), [QUESTION], MODEL, str(archive))
    assert (archive / "Q01.md").read_text() == EXPECTED


def test_a_failed_answer_is_refused(tmp_path, archive):
    dctFailed = {"question_id": "Q01", "model": MODEL, "latency": 1.0, "error": "RateLimitError"}
    save(tmp_path, dctFailed)
    with pytest.raises(ValueError, match="Q01"):
        export_answers(str(tmp_path), [QUESTION], MODEL, str(archive))
    assert not archive.exists()
