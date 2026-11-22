# ABOUTME: Serves a page on this machine on which Tom rates the saved answers without knowing the model.
# ABOUTME: Keeps the order of the models in key.json and saves each rating in ratings.json.

import argparse
import glob
import os
import random

from flask import Flask, abort, jsonify, render_template, request

from answer_models import OUTPUT_DIRECTORY, QUESTIONS_CSV, read_json, read_questions, write_json
from src.answer_html import get_answer_html

RATINGS = ("perfect", "ok", "not_good")
POSITIONS = "ABCDEFGH"


def read_json_or_empty(strPath):
    return read_json(strPath) if os.path.exists(strPath) else {}


def read_answers(strOutput, strId):
    """Gives the answers of a question by model, without the failed ones."""
    lstPaths = glob.glob(os.path.join(strOutput, "answers", f"{strId}_*.json"))
    lstRecords = [read_json(strPath) for strPath in sorted(lstPaths)]
    return {dctRecord["model"]: dctRecord["answer"] for dctRecord in lstRecords
            if "answer" in dctRecord}


def get_key(strOutput, lstQuestions, rng=random):
    """
    Gives the model at each position of each question. The order of a question is drawn once and
    saved in key.json.

    :param strOutput: The directory of the saved answers.
    :param lstQuestions: The questions of the review.
    :param rng: The source of the random order.
    :return: For each question id the models by position letter.
    """
    strPath = os.path.join(strOutput, "key.json")
    dctKey = read_json_or_empty(strPath)
    for dctQuestion in lstQuestions:
        strId = dctQuestion["question_id"]
        lstModels = list(read_answers(strOutput, strId))
        if not lstModels:
            raise ValueError(f"No answer to review for {strId}")
        if strId not in dctKey:
            rng.shuffle(lstModels)
            dctKey[strId] = dict(zip(POSITIONS, lstModels))
        elif sorted(dctKey[strId].values()) != sorted(lstModels):
            raise ValueError(f"The answers of {strId} are not those the key was made for")
    write_json(strPath, dctKey)
    return {dctQuestion["question_id"]: dctKey[dctQuestion["question_id"]]
            for dctQuestion in lstQuestions}


def create_app(strOutput, lstQuestions):
    """
    Creates the review page.

    :param strOutput: The directory of the saved answers.
    :param lstQuestions: The questions to review, in the order shown.
    :return: The Flask app.
    """
    app = Flask(__name__)
    dctKey = get_key(strOutput, lstQuestions)
    strRatingsPath = os.path.join(strOutput, "ratings.json")

    @app.get("/")
    def review():
        dctRatings = read_json_or_empty(strRatingsPath)
        lstShown = []
        for dctQuestion in lstQuestions:
            strId = dctQuestion["question_id"]
            dctAnswers = read_answers(strOutput, strId)
            lstAnswers = [{"position": strPosition,
                           "html": get_answer_html(dctAnswers[strModel]),
                           "rating": dctRatings.get(strId, {}).get(strPosition, {})}
                          for strPosition, strModel in dctKey[strId].items()]
            strPrompt = read_json(os.path.join(strOutput, "prompts", f"{strId}.json"))["prompt"]
            lstShown.append(dctQuestion | {"answers": lstAnswers, "prompt": strPrompt})
        return render_template("review.html", questions=lstShown, ratings=RATINGS)

    @app.post("/rate")
    def rate():
        dctSent = request.get_json()
        strId, strPosition = dctSent.get("question_id"), dctSent.get("position")
        dctRating = {key: dctSent.get(key) for key in ("rating", "factual_error", "note")}
        if strPosition not in dctKey.get(strId, {}) \
                or dctRating["rating"] not in RATINGS + (None,) \
                or not isinstance(dctRating["factual_error"], bool) \
                or not isinstance(dctRating["note"], str):
            abort(400)
        dctRatings = read_json_or_empty(strRatingsPath)
        dctRatings.setdefault(strId, {})[strPosition] = dctRating
        write_json(strRatingsPath, dctRatings)
        return jsonify(saved=True)

    return app


def main():
    parser = argparse.ArgumentParser(description="Serves the page for rating saved answers.")
    parser.add_argument("batch", help="value of the 'use' column, for example batch1")
    parser.add_argument("--ids", nargs="+", help="only these questions of the batch")
    parser.add_argument("--questions", default=QUESTIONS_CSV)
    parser.add_argument("--output", default=OUTPUT_DIRECTORY)
    parser.add_argument("--port", type=int, default=8050)
    args = parser.parse_args()
    app = create_app(os.path.abspath(args.output),
                     read_questions(args.questions, args.batch, args.ids))
    # one thread, so that two ratings sent together are saved one after the other
    app.run(host="127.0.0.1", port=args.port, threaded=False)


if __name__ == "__main__":
    main()
