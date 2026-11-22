# ABOUTME: Writes one model's saved answers to markdown files, one per question, for the archive.
# ABOUTME: Leaves out the prompt, as the document texts in it can hold email addresses.

import argparse
import os

from answer_models import OUTPUT_DIRECTORY, QUESTIONS_CSV, read_json, read_questions

ARCHIVE_DIRECTORY = os.path.join(os.path.dirname(QUESTIONS_CSV), "..", "archive",
                                 "gpt4o_mini_baseline_answers")


def get_markdown(dctPrompt, dctAnswer):
    return f"""# {dctPrompt['question_id']}: {dctPrompt['question']}

- Kind: {dctPrompt['kind']}
- Model: {dctAnswer['model_returned']}
- Prompt tokens: {dctAnswer['prompt_tokens']}
- Completion tokens: {dctAnswer['completion_tokens']}
- Reasoning tokens: {dctAnswer['reasoning_tokens']}
- Latency: {dctAnswer['latency']:.1f} s
- Cost: ${dctAnswer['cost']:.5f}
- Documents: {', '.join(dctPrompt['ids'])}

## Answer

{dctAnswer['answer']}
"""


def export_answers(strOutput, lstQuestions, strModel, strArchive):
    """
    Writes the answers of a model to the archive. An answer already there is never replaced.

    :param strOutput: The directory of the saved answers.
    :param lstQuestions: The questions.
    :param strModel: The model.
    :param strArchive: The directory for the markdown files.
    """
    for dctQuestion in lstQuestions:
        strId = dctQuestion["question_id"]
        dctPrompt = read_json(os.path.join(strOutput, "prompts", f"{strId}.json"))
        dctAnswer = read_json(os.path.join(strOutput, "answers", f"{strId}_{strModel}.json"))
        if "answer" not in dctAnswer:
            raise ValueError(f"{strId} has no answer of {strModel}")
        strMarkdown = get_markdown(dctPrompt, dctAnswer)
        strPath = os.path.join(strArchive, f"{strId}.md")
        if os.path.exists(strPath):
            with open(strPath) as file:
                if file.read() != strMarkdown:
                    raise ValueError(f"{strPath} holds another answer")
            continue
        os.makedirs(strArchive, exist_ok=True)
        with open(strPath, "w") as file:
            file.write(strMarkdown)


def main():
    parser = argparse.ArgumentParser(description="Writes a model's answers to markdown files.")
    parser.add_argument("batch", help="value of the 'use' column, for example batch1")
    parser.add_argument("--ids", nargs="+", help="only these questions of the batch")
    parser.add_argument("--model", default="gpt-4o-mini")
    parser.add_argument("--questions", default=QUESTIONS_CSV)
    parser.add_argument("--output", default=OUTPUT_DIRECTORY)
    parser.add_argument("--archive", default=ARCHIVE_DIRECTORY)
    args = parser.parse_args()
    export_answers(args.output, read_questions(args.questions, args.batch, args.ids), args.model,
                   args.archive)


if __name__ == "__main__":
    main()
