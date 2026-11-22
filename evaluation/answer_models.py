# ABOUTME: Puts the evaluation questions to the models and saves each answer with its figures.
# ABOUTME: Retrieval, prompt and model call are those of production, for a first answer.

import argparse
import csv
import json
import os
import time

import chromadb
import ollama
import openai

from src.llm_functions import FileProcessorThread, build_prompt, get_num_draft_docs
from src.site_config import read_config

DIRECTORY = os.path.dirname(os.path.abspath(__file__))
SITE_DIRECTORY = os.path.join(DIRECTORY, "..", "fwww")
QUESTIONS_CSV = os.path.join(DIRECTORY, "..", "..", "ml", "docs", "plans", "refresh_questions.csv")
OUTPUT_DIRECTORY = os.path.join(DIRECTORY, "..", "data", "evaluation")

# dollars per million tokens, input and output, for standard calls; read on 2026-11-22 from
# https://developers.openai.com/api/docs/pricing
MODEL_PRICES = {
    "gpt-4o-mini": (.15, .60),
    "gpt-6-luna": (.10, .50),
    "gpt-6.1-terra": (1.00, 5.00),
}


def read_questions(strPath, strUse):
    """
    Reads the questions of one batch.

    :param strPath: The path of the question file.
    :param strUse: The value of the 'use' column.
    :return: A list of dictionaries with 'question_id', 'kind' and 'question', in file order.
    """
    with open(strPath, newline="") as file:
        lstRows = [row for row in csv.DictReader(file) if row["use"] == strUse]
    if not lstRows:
        raise ValueError(f"No questions with use {strUse} in {strPath}")
    return [{key: row[key] for key in ("question_id", "kind", "question")} for row in lstRows]


def create_retriever(cfg, strChromaHost, strOllamaHost):
    """
    Creates production's job processor without starting its thread.

    :param cfg: The site settings.
    :param strChromaHost: The host of Chroma.
    :param strOllamaHost: The address of Ollama.
    :return: The processor.
    """
    processor = FileProcessorThread.__new__(FileProcessorThread)
    processor.chromaclient = chromadb.HttpClient(host=strChromaHost)
    processor.ollamaclient = ollama.Client(strOllamaHost)
    processor.set_models(cfg.get("MODELS", "EMBED"), cfg.get("MODELS", "LLM_DRAFT"),
                         cfg.get("MODELS", "LLM_REVISE"))
    processor.set_embed_prefix(cfg.get("PROMPTS", "PREFIX"))
    processor.set_docs_params(cfg.getfloat("RAG", "MAX_DISTANCE"),
                              cfg.getint("RAG", "MIN_DOCUMENTS"),
                              cfg.getint("RAG", "MAX_DOCUMENTS"),
                              cfg.getint("RAG", "MAX_DRAFT_DOCUMENTS"))
    return processor


def get_prompt_record(retriever, dctQuestion):
    """
    Retrieves the documents for a question and builds the prompt of a first answer.

    :param retriever: The job processor.
    :param dctQuestion: The question, with 'question_id' and 'question'.
    :return: The question with the 'ids' of the documents and the 'prompt'.
    """
    strQuestion = dctQuestion["question"]
    rQuery = retriever.get_query_results(strQuestion)
    intDocs = get_num_draft_docs(rQuery, retriever.max_distance, retriever.min_documents,
                                 retriever.max_draft_documents)
    strPrompt = build_prompt({"type": "new", "query": strQuestion},
                             rQuery["documents"][0][:intDocs])
    return dctQuestion | {"ids": rQuery["ids"][0][:intDocs], "prompt": strPrompt}


def ask_model(client, strModel, strPrompt):
    """
    Puts a prompt to a model with the call production makes.

    :param client: The OpenAI client.
    :param strModel: The model. It must have a price.
    :param strPrompt: The prompt.
    :return: A dictionary with the model, the 'answer' or the 'error' that stands in its place,
             and for a call that was answered its tokens and cost in dollars.
    """
    if strModel not in MODEL_PRICES:
        raise ValueError(f"No price for {strModel}")
    dctRecord = {"model": strModel}
    fStart = time.time()
    try:
        completion = client.chat.completions.create(
            model=strModel, messages=[{"role": "user", "content": strPrompt}])
    except openai.OpenAIError as e:
        return dctRecord | {"latency": time.time() - fStart, "error": f"{type(e).__name__}: {e}"}
    dctRecord["latency"] = time.time() - fStart
    usage = completion.usage
    fPriceIn, fPriceOut = MODEL_PRICES[strModel]
    dctRecord["model_returned"] = completion.model
    dctRecord["prompt_tokens"] = usage.prompt_tokens
    dctRecord["completion_tokens"] = usage.completion_tokens
    # reasoning tokens are part of the completion tokens, so the cost already includes them
    details = usage.completion_tokens_details
    dctRecord["reasoning_tokens"] = (details and details.reasoning_tokens) or 0
    dctRecord["cost"] = (usage.prompt_tokens * fPriceIn
                         + usage.completion_tokens * fPriceOut) / 1_000_000
    choice = completion.choices[0]
    if choice.message.content and choice.message.content.strip():
        dctRecord["answer"] = choice.message.content
    else:
        dctRecord["error"] = f"No answer text (finish reason: {choice.finish_reason})"
    return dctRecord


def read_json(strPath):
    with open(strPath) as file:
        return json.load(file)


def write_json(strPath, dctData):
    os.makedirs(os.path.dirname(strPath), exist_ok=True)
    with open(strPath, "w") as file:
        json.dump(dctData, file, indent=2)


def get_saved_prompt(retriever, dctQuestion, strOutput):
    """Gives the saved prompt of a question, after retrieving and saving it the first time."""
    strPath = os.path.join(strOutput, "prompts", f"{dctQuestion['question_id']}.json")
    if not os.path.exists(strPath):
        write_json(strPath, get_prompt_record(retriever, dctQuestion))
    return read_json(strPath)["prompt"]


def run_questions(retriever, client, lstQuestions, lstModels, strOutput):
    """
    Puts every question to every model and saves the answers. An answer that is already saved is
    kept and not paid for again; a failed call is made again.

    :param retriever: The job processor.
    :param client: The OpenAI client.
    :param lstQuestions: The questions.
    :param lstModels: The models.
    :param strOutput: The directory for the saved prompts and answers.
    """
    for dctQuestion in lstQuestions:
        strPrompt = get_saved_prompt(retriever, dctQuestion, strOutput)
        for strModel in lstModels:
            strName = f"{dctQuestion['question_id']}_{strModel}"
            strPath = os.path.join(strOutput, "answers", f"{strName}.json")
            if os.path.exists(strPath) and "answer" in read_json(strPath):
                print(f"{strName}: kept")
                continue
            dctRecord = ask_model(client, strModel, strPrompt)
            write_json(strPath, {"question_id": dctQuestion["question_id"]} | dctRecord)
            if "answer" in dctRecord:
                print(f"{strName}: answered, {dctRecord['latency']:.1f} s, "
                      f"${dctRecord['cost']:.5f}")
            else:
                print(f"{strName}: FAILED, {dctRecord['error']}")


def main():
    parser = argparse.ArgumentParser(description="Puts a batch of questions to models (paid).")
    parser.add_argument("batch", help="value of the 'use' column, for example batch1")
    parser.add_argument("--models", nargs="+", required=True, choices=list(MODEL_PRICES))
    parser.add_argument("--questions", default=QUESTIONS_CSV)
    parser.add_argument("--output", default=OUTPUT_DIRECTORY)
    parser.add_argument("--chroma", default="localhost")
    parser.add_argument("--ollama", default="http://localhost:11434")
    args = parser.parse_args()
    cfg = read_config(SITE_DIRECTORY)
    retriever = create_retriever(cfg, args.chroma, args.ollama)
    run_questions(retriever, openai.OpenAI(api_key=cfg.get("KEYS", "OPENAI")),
                  read_questions(args.questions, args.batch), args.models, args.output)


if __name__ == "__main__":
    main()
