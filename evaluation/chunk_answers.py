# ABOUTME: Puts questions to the model once per chunk-size variant, each given the same number of words (plan 2.6, paid).
# ABOUTME: Writes blind sheets for judging: answers under random letters, the pooled text, the key in a file of its own.

import argparse
import csv
import glob
import json
import os
import random

import chromadb
import ollama
import openai

from answer_models import (OUTPUT_DIRECTORY, QUESTIONS_CSV, SITE_DIRECTORY, ask_model,
                           read_json, write_json)
from src.llm_functions import build_prompt
from src.site_config import read_config

MODEL = "gpt-6-luna"
DOC_PREFIX = "search_document:"
WORD_BUDGET = 3750
CHUNKS_RETRIEVED = 60
VARIANTS = {"A": "words250_overlap0", "B": "words150_overlap0", "C": "words400_overlap0",
            "D": "words250_overlap50", "E": "words400_overlap80"}
# A is asked twice, to show how much two answers from the same prompt differ
RUNS = ["A", "A2", "B", "C", "D", "E"]
LETTERS = "UVWXYZ"
QUESTION_IDS = ["Q02", "Q13", "Q17", "Q28", "Q51"]
RUN_DIRECTORY = os.path.join(OUTPUT_DIRECTORY, "chunk_answers")


def count_words(strDoc):
    """Counts the words of a chunk, leaving out the prefix it was embedded with."""
    return len(strDoc.removeprefix(DOC_PREFIX).split())


def select_within_budget(lstDocs, intBudget):
    """
    Takes chunks in order while their words stay within the budget. The first that does not fit
    ends the list; no chunk is skipped or cut.

    :return: The number of chunks taken and their words.
    """
    intDocs, intWords = 0, 0
    for strDoc in lstDocs:
        intDoc = count_words(strDoc)
        if intWords + intDoc > intBudget:
            break
        intDocs, intWords = intDocs + 1, intWords + intDoc
    if intDocs == 0:
        raise ValueError(f"The first chunk alone is over the budget of {intBudget} words")
    return intDocs, intWords


def get_prompt_record(collection, embed, strQuestion, intBudget):
    """
    Retrieves the chunks of a question in order of distance and builds the prompt of a first
    answer, without numbers, from those within the budget.

    :param embed: Gives the query embeddings of a question.
    :return: A dictionary with the 'ids' and 'docs' given, their 'words' and the 'prompt'.
    """
    rQuery = collection.query(query_embeddings=embed(strQuestion), n_results=CHUNKS_RETRIEVED)
    lstDocs = rQuery["documents"][0]
    intDocs, intWords = select_within_budget(lstDocs, intBudget)
    return {"ids": rQuery["ids"][0][:intDocs], "docs": lstDocs[:intDocs], "words": intWords,
            "prompt": build_prompt({"type": "new", "query": strQuestion}, lstDocs[:intDocs])}


def run_questions(dctCollections, embed, client, lstQuestions, strOutput, intBudget):
    """
    Asks every question once per run and saves each answer with its prompt and figures. An answer
    that is already saved is kept and not paid for again; a failed call is made again.

    :param dctCollections: The collection of each variant, by its letter.
    """
    for dctQuestion in lstQuestions:
        strId = dctQuestion["question_id"]
        dctPrompts = {}
        for strRun in RUNS:
            strVariant = strRun[0]
            strPath = os.path.join(strOutput, "answers", f"{strId}_{strRun}.json")
            if os.path.exists(strPath) and "answer" in read_json(strPath):
                print(f"{strId}_{strRun}: kept")
                continue
            if strVariant not in dctPrompts:
                dctPrompts[strVariant] = get_prompt_record(
                    dctCollections[strVariant], embed, dctQuestion["question"], intBudget)
            dctPrompt = dctPrompts[strVariant]
            dctRecord = ask_model(client, MODEL, dctPrompt["prompt"])
            write_json(strPath, {"question_id": strId, "question": dctQuestion["question"],
                                 "run": strRun, "variant": strVariant,
                                 "collection": VARIANTS[strVariant]} | dctPrompt | dctRecord)
            if "answer" in dctRecord:
                print(f"{strId}_{strRun}: {len(dctPrompt['ids'])} chunks, {dctPrompt['words']} "
                      f"words, {dctRecord['latency']:.1f} s, ${dctRecord['cost']:.5f}")
            else:
                print(f"{strId}_{strRun}: FAILED, {dctRecord['error']}")


def make_sheet(lstRecords, rng):
    """
    Makes the judging sheet of one question: each answer under a random letter, then every chunk
    any of its prompts held, once, in no order of variant.

    :param lstRecords: The answer records of the question, one per run.
    :return: The sheet's text, and the key: the run of each letter.
    """
    lstRuns = [dctRecord["run"] for dctRecord in lstRecords]
    lstShuffled = rng.sample(lstRuns, len(lstRuns))
    dctKey = dict(zip(LETTERS, lstShuffled))
    dctByRun = {dctRecord["run"]: dctRecord for dctRecord in lstRecords}
    lstParts = [f"# {lstRecords[0]['question_id']}: {lstRecords[0]['question']}\n"]
    for strLetter, strRun in dctKey.items():
        lstParts.append(f"## Answer {strLetter}\n\n{dctByRun[strRun]['answer']}\n")
    lstPooled = sorted({strDoc.removeprefix(DOC_PREFIX).strip()
                        for dctRecord in lstRecords for strDoc in dctRecord["docs"]})
    lstParts.append("# Pooled text\n")
    lstParts += [f"---\n{strDoc}\n" for strDoc in lstPooled]
    return "\n".join(lstParts), dctKey


def write_sheets(strOutput, rng):
    """
    Writes one sheet per question from the saved answers, and the key of all of them. Refuses to
    run when a key exists, so the letters judged are never changed.
    """
    strKeyPath = os.path.join(strOutput, "key.json")
    if os.path.exists(strKeyPath):
        raise FileExistsError(f"{strKeyPath} exists; the sheets are not written again")
    dctByQuestion = {}
    for strPath in sorted(glob.glob(os.path.join(strOutput, "answers", "*.json"))):
        dctRecord = read_json(strPath)
        dctByQuestion.setdefault(dctRecord["question_id"], []).append(dctRecord)
    dctKeys = {}
    for strId, lstRecords in dctByQuestion.items():
        if sorted(dctRecord["run"] for dctRecord in lstRecords) != sorted(RUNS):
            raise ValueError(f"{strId} does not have one answer per run")
        strSheet, dctKeys[strId] = make_sheet(lstRecords, rng)
        os.makedirs(os.path.join(strOutput, "sheets"), exist_ok=True)
        with open(os.path.join(strOutput, "sheets", f"{strId}.md"), "w") as file:
            file.write(strSheet)
    write_json(strKeyPath, dctKeys)


def main():
    parser = argparse.ArgumentParser(description="Asks the questions of plan 2.6 once per "
                                                 "chunk-size variant (paid), or writes the sheets.")
    parser.add_argument("--sheets", action="store_true",
                        help="only write the blind sheets from the saved answers; no call is made")
    parser.add_argument("--output", default=RUN_DIRECTORY)
    parser.add_argument("--chroma-port", default="8010")
    parser.add_argument("--ollama", default="http://localhost:11434")
    args = parser.parse_args()
    if args.sheets:
        write_sheets(args.output, random.SystemRandom())
        return
    cfg = read_config(SITE_DIRECTORY)
    chroma = chromadb.HttpClient(host="localhost", port=args.chroma_port)
    dctCollections = {strVariant: chroma.get_collection(strName)
                      for strVariant, strName in VARIANTS.items()}
    ollamaclient = ollama.Client(args.ollama)
    strPrefix, strEmbed = cfg.get("PROMPTS", "PREFIX"), cfg.get("MODELS", "EMBED")

    def embed(strQuestion):
        return ollamaclient.embed(model=strEmbed, input=strPrefix + strQuestion)["embeddings"]

    with open(QUESTIONS_CSV, newline="") as file:
        lstQuestions = [row for row in csv.DictReader(file) if row["question_id"] in QUESTION_IDS]
    run_questions(dctCollections, embed, openai.OpenAI(api_key=cfg.get("KEYS", "OPENAI")),
                  lstQuestions, args.output, WORD_BUDGET)


if __name__ == "__main__":
    main()
