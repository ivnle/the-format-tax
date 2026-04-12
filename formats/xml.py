"""XML format backed by vendored source grammars."""

from functools import lru_cache
from pathlib import Path
from typing import Callable, Optional

from extraction import ExtractionError, extract_first_matching_lark_answer
from prompting import render_prompt, resolve_task_name


NAME = "xml"
_GRAMMARS_DIR = Path(__file__).resolve().parents[1] / "grammars"
ANSWER_PATHS = {
    "math500": ["answer", "text"],
    "gpqa": ["answer"],
    "zebralogic": ["answer"],
}


def wrap_prompt(task_instruction: str, question: str) -> str:
    task_name = resolve_task_name(task_instruction)
    return render_prompt(
        task_instruction=task_instruction,
        question=question,
        format_name=NAME,
        grammar=load_grammar(task_name),
    )


def extract_answer(
    raw_output: str,
    task_fallback_extractor: Optional[Callable[[str], str]] = None,
) -> str:
    try:
        return extract_first_matching_lark_answer(
            raw_output,
            (
                (load_grammar(task_name), answer_path)
                for task_name, answer_path in ANSWER_PATHS.items()
            ),
        )
    except Exception:
        if task_fallback_extractor is not None:
            return task_fallback_extractor(raw_output)
        return ""


@lru_cache(maxsize=3)
def load_grammar(task_name: str) -> str:
    path = _GRAMMARS_DIR / task_name / "xml.lark"
    with open(path, encoding="utf-8") as handle:
        return handle.read()
