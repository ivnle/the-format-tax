"""Freeform prompt wrapper for the public release."""

from typing import Callable, Optional

from prompting import render_prompt


NAME = "freeform"


def wrap_prompt(task_instruction: str, question: str) -> str:
    return render_prompt(
        task_instruction=task_instruction,
        question=question,
        format_name=NAME,
    )


def extract_answer(
    raw_output: str,
    task_fallback_extractor: Optional[Callable[[str], str]] = None,
) -> str:
    if task_fallback_extractor is None:
        return raw_output.strip()
    return task_fallback_extractor(raw_output)


def load_grammar(task_name: str) -> None:
    del task_name
    return None
