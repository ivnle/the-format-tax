#!/usr/bin/env python3
"""Render all 15 (task, format) prompts using one real example per task.

Loads one real question from each of MATH-500, GPQA-Diamond, and ZebraLogic,
truncates the question text to ~600 chars if needed (preserving the rest of
the prompt verbatim), and prints all 15 rendered prompts to stdout with a
banner per prompt. Useful for eyeballing the actual public-release prompt
contract.

Usage:
    cd <release dir> && uv run python dev/show_prompts.py
    cd <release dir> && uv run python dev/show_prompts.py --max-question-chars 300
    cd <release dir> && uv run python dev/show_prompts.py --tasks math500
"""

from __future__ import annotations

import argparse
import sys
import textwrap
from pathlib import Path

RELEASE_DIR = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(RELEASE_DIR))

from formats import FORMATS  # noqa: E402
from tasks import TASKS  # noqa: E402


FORMAT_ORDER = ["freeform", "json", "xml", "latex", "markdown"]
TASK_ORDER = ["math500", "gpqa", "zebralogic"]


def truncate_question(text: str, max_chars: int) -> str:
    if len(text) <= max_chars:
        return text
    head = text[: max_chars // 2]
    tail = text[-max_chars // 2 :]
    return f"{head}\n\n[... truncated {len(text) - max_chars} chars ...]\n\n{tail}"


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--max-question-chars",
        type=int,
        default=600,
        help="Truncate the question body to this many chars (default: 600).",
    )
    parser.add_argument(
        "--tasks",
        nargs="+",
        choices=TASK_ORDER,
        default=TASK_ORDER,
        help="Restrict to a subset of tasks.",
    )
    parser.add_argument(
        "--formats",
        nargs="+",
        choices=FORMAT_ORDER,
        default=FORMAT_ORDER,
        help="Restrict to a subset of formats.",
    )
    return parser.parse_args()


def main() -> None:
    args = parse_args()

    sample_questions: dict[str, str] = {}
    for task_name in args.tasks:
        examples = TASKS[task_name].load_examples(max_examples=1)
        if not examples:
            raise RuntimeError(f"No examples returned for task {task_name!r}.")
        sample_questions[task_name] = examples[0].question

    counter = 0
    total = len(args.tasks) * len(args.formats)
    for task_name in args.tasks:
        question = truncate_question(sample_questions[task_name], args.max_question_chars)
        for format_name in args.formats:
            counter += 1
            banner = f"# {counter}/{total}  task={task_name}  format={format_name}"
            print("=" * len(banner))
            print(banner)
            print("=" * len(banner))
            rendered = FORMATS[format_name].wrap_prompt(
                TASKS[task_name].INSTRUCTION,
                question,
            )
            print(rendered)
            print()


if __name__ == "__main__":
    main()
