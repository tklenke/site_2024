# ABOUTME: Counts Tom's ratings per model and puts each model's time, tokens and cost beside them.
# ABOUTME: Shows nothing until every answer of the questions is rated, as it names the models.

import argparse
import glob
import os
import statistics

from answer_models import OUTPUT_DIRECTORY, QUESTIONS_CSV, read_json, read_questions
from review_answers import RATINGS, read_json_or_empty

COLUMNS = ("model", "perfect", "ok", "not_good", "errors", "failed", "median_s", "reasoning",
           "$/answer")


def check_all_rated(dctKey, dctRatings, lstIds):
    lstMissing = [strId for strId in lstIds if strId not in dctKey]
    lstMissing += [f"{strId}-{strPosition}" for strId in lstIds
                   for strPosition in dctKey.get(strId, {})
                   if not dctRatings.get(strId, {}).get(strPosition, {}).get("rating")]
    if lstMissing:
        raise ValueError(f"Not rated yet: {', '.join(lstMissing)}")


def get_tally(strOutput, lstQuestions):
    """
    Counts the ratings of each model and computes its figures.

    :param strOutput: The directory of the saved answers, the key and the ratings.
    :param lstQuestions: The questions to count.
    :return: A dictionary of the counts and figures by model.
    """
    lstIds = [dctQuestion["question_id"] for dctQuestion in lstQuestions]
    dctKey = read_json_or_empty(os.path.join(strOutput, "key.json"))
    dctRatings = read_json_or_empty(os.path.join(strOutput, "ratings.json"))
    check_all_rated(dctKey, dctRatings, lstIds)

    dctAnswers = {}
    for strId in lstIds:
        for strPath in glob.glob(os.path.join(strOutput, "answers", f"{strId}_*.json")):
            dctAnswer = read_json(strPath)
            dctAnswers.setdefault(dctAnswer["model"], []).append(dctAnswer)
    dctRated = {strModel: [] for strModel in dctAnswers}
    for strId in lstIds:
        for strPosition, strModel in dctKey[strId].items():
            dctRated[strModel].append(dctRatings[strId][strPosition])

    dctTally = {}
    for strModel in sorted(dctAnswers):
        lstAnswered = [dctAnswer for dctAnswer in dctAnswers[strModel] if "answer" in dctAnswer]
        dctTally[strModel] = {strRating: sum(dctRating["rating"] == strRating
                                             for dctRating in dctRated[strModel])
                              for strRating in RATINGS}
        dctTally[strModel] |= {
            "factual_errors": sum(dctRating["factual_error"] for dctRating in dctRated[strModel]),
            "failed": len(dctAnswers[strModel]) - len(lstAnswered),
            "median_latency": statistics.median(d["latency"] for d in lstAnswered),
            "median_reasoning_tokens": statistics.median(d["reasoning_tokens"]
                                                         for d in lstAnswered),
            "cost_per_answer": statistics.mean(d["cost"] for d in lstAnswered)}
    return dctTally


def get_tally_text(dctTally):
    lstRows = [COLUMNS]
    for strModel, dctRow in dctTally.items():
        lstRows.append((strModel, *(str(dctRow[strRating]) for strRating in RATINGS),
                        str(dctRow["factual_errors"]), str(dctRow["failed"]),
                        f"{dctRow['median_latency']:.1f}",
                        f"{dctRow['median_reasoning_tokens']:.0f}",
                        f"{dctRow['cost_per_answer']:.5f}"))
    return "\n".join(f"{row[0]:<15}" + "".join(f"{cell:>10}" for cell in row[1:])
                     for row in lstRows)


def main():
    parser = argparse.ArgumentParser(description="Shows the tally of rated batches.")
    parser.add_argument("batches", nargs="+", help="values of the 'use' column")
    parser.add_argument("--questions", default=QUESTIONS_CSV)
    parser.add_argument("--output", default=OUTPUT_DIRECTORY)
    args = parser.parse_args()
    lstQuestions = [dctQuestion for strBatch in args.batches
                    for dctQuestion in read_questions(args.questions, strBatch)]
    print(get_tally_text(get_tally(args.output, lstQuestions)))


if __name__ == "__main__":
    main()
