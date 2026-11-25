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


# ---- numbered chunks (plan 4.1a)
# the prompts as they were before chunks could be numbered, character for character
UNNUMBERED = {
    "new": " Q?  Use the following pieces of context to answer the users question about a Cozy "
           "amatuer-build aircraft. -----  c1\n\nc2",
    "revise": "You are the refinement model.\nReview the user's question about a Cozy amatuer-build "
              "aircraft, the draft response and the retrieved context.\nYour task is to verify "
              "factual accuracy, add missing technical detail, and correct any mistakes.\nCite or "
              "reference relevant context when useful.\nIf the draft is already correct, restate it "
              "concisely.\n USER QUESTION Q? \n                            DRAFT RESPONSE: A. \n"
              "                            RETRIEVED CONTENT: c1\n\nc2",
    "followup": "You are the refinement model.\nReview the user's follow up question, the draft "
                "response, the previous context provided \nfor the draft response, and the "
                "additional content based on the followup question.\nYour task is to answer the "
                "follow up question to the draft response using the additional content\nand "
                "previous content as context.\n USER QUESTION: Q?\n                        DRAFT "
                "RESPONSE: A. PREVIOUS CONTENT: c1\n\nc2\n                        "
                "ADDITIONAL_CONTENT: c3",
}
# the wording of plan 4.1a
CITATION = ("Each piece of context starts with its number in square brackets. After a statement "
            "that you take from the context, write the number of the piece it comes from in "
            "square brackets, like this: [3]. For more than one piece write [2][5]. Use only the "
            "numbers given. Do not write a list of sources at the end.")


def short_job(strType):
    return {"type": strType, "query": "Q?", "result": {"answer": "A."}}


@pytest.mark.parametrize("strType", ["new", "revise", "followup"])
@pytest.mark.parametrize("dctNumbering", [{}, {"numbered": False}])
def test_prompts_with_numbering_off_are_unchanged(strType, dctNumbering):
    assert build_prompt(short_job(strType), ["c1", "c2"], ["c3"], **dctNumbering) == \
        UNNUMBERED[strType]


def test_numbered_new_question_prompt():
    assert build_prompt(short_job("new"), ["c1", "c2"], numbered=True) == (
        " Q?  Use the following pieces of context to answer the users question about a Cozy "
        f"amatuer-build aircraft. {CITATION} -----  [1] c1\n\n[2] c2")


def test_numbered_revise_prompt():
    assert build_prompt(short_job("revise"), ["c1", "c2"], numbered=True) == (
        UNNUMBERED["revise"]
        .replace("concisely.\n", f"concisely.\n{CITATION}\n")
        .replace("c1\n\nc2", "[1] c1\n\n[2] c2"))


def test_numbered_followup_prompt_counts_on_in_the_additional_content():
    assert build_prompt(short_job("followup"), ["c1", "c2"], ["c3", "c4"], numbered=True) == (
        UNNUMBERED["followup"]
        .replace("as context.\n", f"as context.\n{CITATION}\n")
        .replace("c1\n\nc2", "[1] c1\n\n[2] c2")
        .replace("c3", "[3] c3\n\n[4] c4"))


def test_numbered_followup_prompt_without_additional_documents():
    strPrompt = build_prompt(short_job("followup"), ["c1", "c2"], [], numbered=True)
    assert strPrompt.endswith(f"PREVIOUS CONTENT: [1] c1\n\n[2] c2\n                        "
                              f"ADDITIONAL_CONTENT: {no_additional_content}")
