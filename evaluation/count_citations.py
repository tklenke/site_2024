# ABOUTME: Counts the citations in the answers of the trial of numbered chunks (plan 4.1a).
# ABOUTME: Lists answers without a number, numbers that name no chunk and citations in another form.

import glob
import os
import re
import statistics

from answer_models import OUTPUT_DIRECTORY, read_json
from cite_trial import MODEL, TRIAL_DIRECTORY

RATED_DIRECTORY = os.path.join(OUTPUT_DIRECTORY, "answers")
REPORT_PATH = os.path.join(OUTPUT_DIRECTORY, "cite_trial_count.md")

# [3], or [2, 5]; not the text of a markdown link, which is followed by its address
CITATION = re.compile(r"\[(\d+(?:\s*,\s*\d+)*)\](?!\()")
# a bracket that holds a digit and other text, again not the text of a link
OTHER_BRACKET = re.compile(r"\[[^\[\]\n]*\d[^\[\]\n]*\](?!\()")
# a parenthesis that holds only numbers, or a number and a word that names a piece of context;
# a figure with its unit, as in (5.15 m), is not a citation
OTHER_PARENTHESIS = re.compile(
    r"\(\s*\d+(?:\s*,\s*\d+)*\s*\)"
    r"|\([^()\n]*\b(?:sources?|pieces?|context|chunks?|docs?|documents?|ref|references?)\b"
    r"[^()\n]*\d[^()\n]*\)", re.IGNORECASE)
# a line that opens a list of sources
SOURCE_LIST = re.compile(r"^\W*(?:sources|references|citations)\b", re.IGNORECASE | re.MULTILINE)
FIGURES = ["prompt_tokens", "completion_tokens", "reasoning_tokens", "latency", "cost"]
FIGURE_FORMATS = {"latency": "{:.2f}", "cost": "{:.5f}"}


def find_numbers(strAnswer):
    """The chunk numbers cited in the form asked for, or as [2, 5], in the order written."""
    return [int(strNumber) for match in CITATION.finditer(strAnswer)
            for strNumber in match.group(1).split(",")]


def find_other_forms(strAnswer):
    """The texts that look like a citation and are not in the form asked for, in the order written."""
    lstMatches = [match for match in OTHER_BRACKET.finditer(strAnswer)
                  if not CITATION.fullmatch(match.group())]
    lstMatches += list(OTHER_PARENTHESIS.finditer(strAnswer))
    return [match.group() for match in sorted(lstMatches, key=lambda match: match.start())]


def has_source_list(strAnswer):
    return SOURCE_LIST.search(strAnswer) is not None


def count_answer(dctAnswer):
    """The citations of one answer, against the number of chunks sent with it."""
    lstNumbers = find_numbers(dctAnswer["answer"])
    intSent = len(dctAnswer["ids"])
    lstValid = [intNumber for intNumber in lstNumbers if 1 <= intNumber <= intSent]
    return {"question_id": dctAnswer["question_id"], "numbers": len(lstNumbers),
            "distinct": len(set(lstValid)), "sent": intSent,
            "no_chunk": [intNumber for intNumber in lstNumbers if intNumber not in lstValid],
            "other_forms": find_other_forms(dctAnswer["answer"]),
            "source_list": has_source_list(dctAnswer["answer"])}


def median_figures(lstAnswers):
    """The median of each figure over the answers that have it."""
    return {strFigure: statistics.median(d[strFigure] for d in lstAnswers if strFigure in d)
            for strFigure in FIGURES if any(strFigure in d for d in lstAnswers)}


def listed(strTitle, lstItems):
    return f"- {strTitle} ({len(lstItems)}): {', '.join(lstItems) or 'none'}"


def report(lstAnswers, dctRated):
    """
    The report of the count, in markdown.

    :param lstAnswers: The answers of the trial.
    :param dctRated: The rated answers of the same model, by question id.
    """
    lstCounts = [count_answer(dctAnswer) for dctAnswer in lstAnswers]
    lstLines = [f"# Count of the citations: {len(lstCounts)} answers of {MODEL}", "",
                listed("Answers without a number",
                       [c["question_id"] for c in lstCounts if not c["numbers"]]),
                listed("Numbers that name no chunk",
                       [c["question_id"] + " " + "".join(f"[{n}]" for n in c["no_chunk"])
                        for c in lstCounts if c["no_chunk"]]),
                listed("Citations in another form",
                       [c["question_id"] + " " + " ".join(c["other_forms"])
                        for c in lstCounts if c["other_forms"]]),
                listed("Lists of sources", [c["question_id"] for c in lstCounts if c["source_list"]]),
                "", "| question | numbers written | distinct chunks cited | chunks sent |",
                "|---|---|---|---|"]
    lstLines += [f"| {c['question_id']} | {c['numbers']} | {c['distinct']} | {c['sent']} |"
                 for c in lstCounts]
    dctTrial = median_figures(lstAnswers)
    dctRatedMedians = median_figures([dctRated[d["question_id"]] for d in lstAnswers
                                      if d["question_id"] in dctRated])
    lstLines += ["", f"Medians over the same questions ({len(dctRated)} rated answers found):", "",
                 "| figure | trial | rated |", "|---|---|---|"]
    for strFigure in dctTrial:
        strFormat = FIGURE_FORMATS.get(strFigure, "{:.0f}")
        strRated = strFormat.format(dctRatedMedians[strFigure]) \
            if strFigure in dctRatedMedians else "none"
        lstLines.append(f"| {strFigure} | {strFormat.format(dctTrial[strFigure])} | {strRated} |")
    return "\n".join(lstLines) + "\n"


def read_answers(strTrial, strRated):
    """The answers of the trial in question order, and the rated answers of the same questions."""
    lstAnswers = sorted((read_json(strPath)
                         for strPath in glob.glob(os.path.join(strTrial, f"*_{MODEL}.json"))),
                        key=lambda d: d["question_id"])
    dctRated = {}
    for dctAnswer in lstAnswers:
        strPath = os.path.join(strRated, f"{dctAnswer['question_id']}_{MODEL}.json")
        if os.path.exists(strPath):
            dctRated[dctAnswer["question_id"]] = read_json(strPath)
    return lstAnswers, dctRated


def main():
    strReport = report(*read_answers(TRIAL_DIRECTORY, RATED_DIRECTORY))
    with open(REPORT_PATH, "w") as file:
        file.write(strReport)
    print(strReport, end="")


if __name__ == "__main__":
    main()
