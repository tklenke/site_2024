# ABOUTME: Tests the prompts sent to the models for new questions, revisions and follow-ups.
# ABOUTME: Checks which document texts each prompt contains and where they are placed.

import pytest

from src.llm_functions import build_prompt, followup_prompt, initial_prompt, \
    no_additional_content, revise_prompt, secondary_prompt

QUESTION = "how many seats does the cozy have"
ANSWER = "It has four seats."


def job_data(strType):
    return {"type": strType, "query": QUESTION, "result": {"answer": ANSWER}}


def test_new_question_prompt():
    strPrompt = build_prompt(job_data("new"), ["first chunk", "second chunk"])
    assert strPrompt == (f"{initial_prompt} {QUESTION} {secondary_prompt} "
                         "first chunk\n\nsecond chunk")


def test_revise_prompt():
    strPrompt = build_prompt(job_data("revise"), ["first chunk", "second chunk"])
    assert strPrompt.split() == (f"{revise_prompt} USER QUESTION {QUESTION} "
                                 f"DRAFT RESPONSE: {ANSWER} "
                                 "RETRIEVED CONTENT: first chunk second chunk").split()
    assert "first chunk\n\nsecond chunk" in strPrompt


def test_followup_prompt():
    strPrompt = build_prompt(job_data("followup"), ["first chunk", "second chunk"],
                             ["third chunk", "fourth chunk"])
    assert strPrompt.split() == (f"{followup_prompt} USER QUESTION: {QUESTION} "
                                 f"DRAFT RESPONSE: {ANSWER} "
                                 "PREVIOUS CONTENT: first chunk second chunk "
                                 "ADDITIONAL_CONTENT: third chunk fourth chunk").split()
    assert "first chunk\n\nsecond chunk" in strPrompt
    assert "third chunk\n\nfourth chunk" in strPrompt


def test_followup_prompt_without_additional_documents():
    strPrompt = build_prompt(job_data("followup"), ["first chunk", "second chunk"], [])
    assert strPrompt.split() == (f"{followup_prompt} USER QUESTION: {QUESTION} "
                                 f"DRAFT RESPONSE: {ANSWER} "
                                 "PREVIOUS CONTENT: first chunk second chunk "
                                 f"ADDITIONAL_CONTENT: {no_additional_content}").split()


@pytest.mark.parametrize("strPrompt", [initial_prompt, secondary_prompt, revise_prompt,
                                       followup_prompt])
def test_prompt_names_no_model(strPrompt):
    assert "gpt" not in strPrompt.lower()
