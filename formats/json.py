"""JSON format backed by vendored source-faithful schemas."""

import json
from functools import lru_cache
from pathlib import Path
from typing import Callable, Optional

from extraction import ExtractionError, extract_answer_from_json
from prompting import render_prompt, resolve_task_name


NAME = "json"
_GRAMMARS_DIR = Path(__file__).resolve().parents[1] / "grammars"
ANSWER_PATH = ["answer"]


def wrap_prompt(task_instruction: str, question: str) -> str:
    task_name = resolve_task_name(task_instruction)
    return render_prompt(
        task_instruction=task_instruction,
        question=question,
        format_name=NAME,
        schema=load_grammar(task_name),
    )


def extract_answer(
    raw_output: str,
    task_fallback_extractor: Optional[Callable[[str], str]] = None,
) -> str:
    try:
        return extract_answer_from_json(raw_output, ANSWER_PATH)
    except ExtractionError:
        if task_fallback_extractor is not None:
            return task_fallback_extractor(raw_output)
        return ""


@lru_cache(maxsize=3)
def load_grammar(task_name: str) -> dict:
    path = _GRAMMARS_DIR / task_name / "json.json"
    with open(path, encoding="utf-8") as handle:
        return json.load(handle)


__all__ = ["ANSWER_PATH", "NAME", "extract_answer", "load_grammar", "wrap_prompt"]
