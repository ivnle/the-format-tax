"""Shared JSON and Lark extraction helpers for the public release."""

from __future__ import annotations

import json
import re
import signal
from functools import lru_cache
from typing import Any, Iterable


class ExtractionError(Exception):
    """Raised when structured answer extraction fails."""


class ExtractionTimeout(ExtractionError):
    """Raised when extraction exceeds the configured time budget.

    Lark's Earley parser can blow up exponentially on pathological model
    outputs. This timeout bounds the cost and ensures a single bad
    record can't stall an entire generation run.
    """


DEFAULT_LARK_TIMEOUT_SECONDS = 10


class _AlarmTimeout:
    """Context manager that raises ExtractionTimeout after `seconds`.

    Uses signal.SIGALRM so it can interrupt long-running pure-Python
    loops (like Earley parsing). Only safe in the main thread on Unix —
    which is where generate.py runs extract_answer.
    """

    def __init__(self, seconds: int):
        self.seconds = seconds
        self._prev_handler = None

    def __enter__(self):
        def _handler(signum, frame):
            raise ExtractionTimeout(
                f"extraction exceeded {self.seconds}s time budget"
            )

        self._prev_handler = signal.signal(signal.SIGALRM, _handler)
        signal.alarm(self.seconds)
        return self

    def __exit__(self, exc_type, exc, tb):
        signal.alarm(0)
        signal.signal(signal.SIGALRM, self._prev_handler)
        return False


def extract_json_payload(response_text: str) -> Any:
    """Extract a JSON payload from raw model output."""
    text = response_text.strip()

    for candidate in (text, *_extract_json_code_blocks(text), _extract_json_span(text)):
        if not candidate:
            continue
        try:
            return json.loads(candidate)
        except json.JSONDecodeError:
            continue

    raise ExtractionError("Could not parse JSON response.")


def extract_answer_from_json(response_text: str, answer_path: list[str]) -> str:
    """Extract an answer value from JSON output by path."""
    current = extract_json_payload(response_text)
    try:
        for key in answer_path:
            current = current[key]
    except (KeyError, IndexError, TypeError) as exc:
        raise ExtractionError(
            f"Could not follow JSON answer path {answer_path!r}."
        ) from exc

    if current is None:
        return ""
    if isinstance(current, str):
        return current.strip()
    if isinstance(current, (dict, list)):
        return json.dumps(current, ensure_ascii=True, sort_keys=True)
    return str(current).strip()


def _extract_json_code_blocks(text: str) -> list[str]:
    pattern = r"```(?:json)?\s*([\s\S]*?)\s*```"
    return [match.strip() for match in re.findall(pattern, text, flags=re.IGNORECASE)]


def _extract_json_span(text: str) -> str | None:
    brace_start = text.find("{")
    brace_end = text.rfind("}")
    if brace_start != -1 and brace_end > brace_start:
        return text[brace_start : brace_end + 1]
    return None


@lru_cache(maxsize=32)
def _get_lark_parser(grammar: str):
    from lark import Lark

    return Lark(grammar, start="start", parser="earley", propagate_positions=True)


def extract_answer_from_lark(
    response_text: str,
    *,
    grammar: str,
    answer_path: list[str],
    timeout_seconds: int = DEFAULT_LARK_TIMEOUT_SECONDS,
) -> str:
    """Parse with a Lark grammar and extract text via a tree path.

    Bounded by `timeout_seconds` (default 10s) via SIGALRM. Raises
    ExtractionTimeout (a subclass of ExtractionError) on timeout, so
    callers that catch ExtractionError will fall through to their
    fallback extractor on pathological inputs.
    """
    parser = _get_lark_parser(grammar)
    with _AlarmTimeout(timeout_seconds):
        tree = parser.parse(response_text)
        return _extract_text_from_tree(tree, answer_path, response_text).strip()


def extract_first_matching_lark_answer(
    response_text: str,
    candidates: Iterable[tuple[str, list[str]]],
) -> str:
    """Try multiple grammar/path pairs and return the first successful extraction."""
    last_error: Exception | None = None
    for grammar, answer_path in candidates:
        try:
            return extract_answer_from_lark(
                response_text,
                grammar=grammar,
                answer_path=answer_path,
            )
        except Exception as exc:  # pragma: no cover - exercised by integration-style checks
            last_error = exc
    raise ExtractionError("No candidate grammar could parse the response.") from last_error


def _extract_text_from_tree(tree, path: list[str], source: str) -> str:
    from lark import Token, Tree

    current = tree
    for rule_name in path:
        if not isinstance(current, Tree):
            raise ExtractionError(f"Cannot descend into non-tree node at {rule_name!r}.")

        for child in current.children:
            if isinstance(child, Tree) and child.data == rule_name:
                current = child
                break
        else:
            raise ExtractionError(f"Missing rule {rule_name!r} in parse tree.")

    return _extract_span(current, source)


def _extract_span(node, source: str) -> str:
    from lark import Token, Tree

    if isinstance(node, Token):
        return str(node)
    if isinstance(node, Tree) and not node.meta.empty:
        if node.meta.start_pos is not None and node.meta.end_pos is not None:
            return source[node.meta.start_pos : node.meta.end_pos]
    return _extract_all_text(node)


def _extract_all_text(node) -> str:
    from lark import Token, Tree

    if isinstance(node, Token):
        return str(node)
    if isinstance(node, Tree):
        return "".join(_extract_all_text(child) for child in node.children)
    return str(node)
