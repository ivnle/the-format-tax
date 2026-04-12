"""MATH-500 task metadata and fallback extraction."""

import re
from dataclasses import dataclass
from typing import Optional

from datasets import load_dataset


NAME = "math500"
INSTRUCTION = "Solve the following math problem."


@dataclass
class Example:
    id: str
    question: str
    gold_answer: str


def load_examples(max_examples: Optional[int] = None) -> list[Example]:
    """Load MATH-500 from HuggingFace (HuggingFaceH4/MATH-500)."""
    ds = load_dataset("HuggingFaceH4/MATH-500", split="test")
    examples = []
    for i, item in enumerate(ds):
        if max_examples is not None and i >= max_examples:
            break
        gold = _extract_boxed(item.get("answer", "")) or item.get("answer", "")
        examples.append(Example(id=str(i), question=item["problem"], gold_answer=gold))
    return examples


def extract_answer_fallback(text: str) -> str:
    """Last-resort answer extraction from a model response."""
    boxed = _extract_boxed(text)
    if boxed is not None:
        return _strip_prose_wrapper(boxed)

    for pattern in [
        r"\\answer\{([^}]*)\}",
        r"<answer>\s*(.*?)\s*</answer>",
        r'"answer"\s*:\s*"([^"]*)"',
    ]:
        matches = list(re.finditer(pattern, text, re.DOTALL | re.IGNORECASE))
        if matches:
            return _strip_prose_wrapper(matches[-1].group(1).strip())

    m = re.search(
        r"(?:answer|result)\s*(?:is|=)\s*(.+?)(?:\.|$)",
        text,
        re.IGNORECASE | re.DOTALL,
    )
    if m:
        return _strip_prose_wrapper(m.group(1).strip())
    lines = [l.strip() for l in text.strip().splitlines() if l.strip()]
    return _strip_prose_wrapper(lines[-1]) if lines else ""


# --- helpers ---

def _extract_boxed(text: str) -> Optional[str]:
    """Extract content from the last \\boxed{} in text, handling nested braces."""
    matches = list(re.finditer(r"\\boxed\{", text))
    if not matches:
        return None
    start = matches[-1].end()
    depth = 1
    pos = start
    while pos < len(text) and depth > 0:
        if text[pos] == "{":
            depth += 1
        elif text[pos] == "}":
            depth -= 1
        pos += 1
    if depth == 0:
        return text[start : pos - 1]
    return None


def _strip_prose_wrapper(text: str) -> str:
    candidate = text.strip()
    for pattern in [
        r"^(?:Therefore,?\s+)?(?:the|The)\s+answer\s+is\s+(.+?)\.?\s*$",
        r"^[Ff]inal\s+answer[:\s]+(?:is\s+)?(.+?)\.?\s*$",
        r'^(?:The\s+value\s+is\s+)?(.+?)\.?\s*$',
    ]:
        match = re.match(pattern, candidate, re.DOTALL)
        if match:
            candidate = match.group(1).strip()
            break

    candidate = re.sub(r"^\$+|\$+$", "", candidate)
    candidate = re.sub(r"\\text\{([^}]*)\}", r"\1", candidate)
    candidate = candidate.replace("\\dfrac", "\\frac").replace("\\tfrac", "\\frac")
    return " ".join(candidate.split())
