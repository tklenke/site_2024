# ABOUTME: Puts the evaluation's questions to the model again with numbered chunks (plan 4.1a, paid).
# ABOUTME: The chunks are fetched by the ids saved with each prompt; a question they no longer fit is left out.

import argparse
import glob
import os

import chromadb
import openai

from answer_models import OUTPUT_DIRECTORY, SITE_DIRECTORY, ask_model, read_json, write_json
from src.llm_functions import build_prompt, get_docs_in_order
from src.site_config import read_config

MODEL = "gpt-6-luna"
PROMPTS_DIRECTORY = os.path.join(OUTPUT_DIRECTORY, "prompts")
TRIAL_DIRECTORY = os.path.join(OUTPUT_DIRECTORY, "cite_trial")


def check_prompts(collection, lstSaved):
    """
    Builds the numbered prompt of each saved prompt record, from the chunks fetched by its ids.
    Built without numbers, the prompt must be the saved one; otherwise the question is left out.

    :param collection: The document collection.
    :param lstSaved: The saved prompt records, with 'question_id', 'question', 'ids' and 'prompt'.
    :return: The numbered prompts by question id, and the reasons of those left out by question id.
    """
    dctPrompts, dctLeftOut = {}, {}
    for dctSaved in lstSaved:
        strId = dctSaved["question_id"]
        docs = get_docs_in_order(collection, dctSaved["ids"])
        lstMissing = [strDoc for strDoc in dctSaved["ids"] if strDoc not in docs["ids"]]
        dctJob = {"type": "new", "query": dctSaved["question"]}
        if lstMissing:
            dctLeftOut[strId] = f"not in the collection: {', '.join(lstMissing)}"
        elif build_prompt(dctJob, docs["documents"]) != dctSaved["prompt"]:
            dctLeftOut[strId] = "the chunks give another prompt than the saved one"
        else:
            dctPrompts[strId] = build_prompt(dctJob, docs["documents"], numbered=True)
    return dctPrompts, dctLeftOut


def report_check(collection, lstSaved):
    """Checks the saved prompts and prints the questions left out and how many are left to ask."""
    dctPrompts, dctLeftOut = check_prompts(collection, lstSaved)
    for strId, strReason in dctLeftOut.items():
        print(f"{strId}: left out, {strReason}")
    print(f"{len(dctPrompts)} of {len(lstSaved)} questions to ask")
    return dctPrompts, dctLeftOut


def run_trial(collection, client, lstSaved, strOutput):
    """
    Checks every saved prompt, then asks the model each numbered prompt and saves the answers.
    An answer that is already saved is kept and not paid for again; a failed call is made again.

    :return: The reasons of the questions left out, by question id.
    """
    dctPrompts, dctLeftOut = report_check(collection, lstSaved)
    for dctSaved in lstSaved:
        strId = dctSaved["question_id"]
        if strId not in dctPrompts:
            continue
        strPath = os.path.join(strOutput, f"{strId}_{MODEL}.json")
        if os.path.exists(strPath) and "answer" in read_json(strPath):
            print(f"{strId}: kept")
            continue
        dctRecord = ask_model(client, MODEL, dctPrompts[strId])
        write_json(strPath, {"question_id": strId, "ids": dctSaved["ids"], "numbered_docs": True,
                             "prompt": dctPrompts[strId]} | dctRecord)
        if "answer" in dctRecord:
            print(f"{strId}: answered, {dctRecord['latency']:.1f} s, ${dctRecord['cost']:.5f}")
        else:
            print(f"{strId}: FAILED, {dctRecord['error']}")
    return dctLeftOut


def main():
    parser = argparse.ArgumentParser(description="Asks the evaluation's questions with numbered "
                                                 "chunks (paid, unless --check).")
    parser.add_argument("--check", action="store_true",
                        help="only check the saved prompts; no call is made")
    parser.add_argument("--output", default=TRIAL_DIRECTORY)
    parser.add_argument("--chroma", default="localhost")
    args = parser.parse_args()
    cfg = read_config(SITE_DIRECTORY)
    collection = chromadb.HttpClient(host=args.chroma).get_collection(cfg.get("MODELS", "EMBED"))
    lstSaved = [read_json(strPath)
                for strPath in sorted(glob.glob(os.path.join(PROMPTS_DIRECTORY, "*.json")))]
    if args.check:
        report_check(collection, lstSaved)
        return
    run_trial(collection, openai.OpenAI(api_key=cfg.get("KEYS", "OPENAI")), lstSaved, args.output)


if __name__ == "__main__":
    main()
