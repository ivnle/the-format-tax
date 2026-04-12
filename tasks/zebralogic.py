"""ZebraLogic task metadata and fallback extraction."""

import re
from dataclasses import dataclass
from typing import Optional

from datasets import load_dataset


NAME = "zebralogic"
INSTRUCTION = "Solve the following logic puzzle."


@dataclass
class Example:
    id: str
    question: str  # includes puzzle + choices
    gold_answer: str  # letter A-F


def load_examples(max_examples: Optional[int] = None) -> list[Example]:
    """Load ZebraLogic from HuggingFace (WildEval/ZebraLogic, mc_mode)."""
    ds = load_dataset("WildEval/ZebraLogic", "mc_mode", split="test")

    letter_labels = ["A", "B", "C", "D", "E", "F"]
    examples = []
    for i, item in enumerate(ds):
        if max_examples is not None and i >= max_examples:
            break

        puzzle = item.get("puzzle", "")
        question = item.get("question", "")
        choices = item.get("choices", [])
        answer_text = item.get("answer", "")

        formatted_choices = []
        for idx, choice in enumerate(choices):
            if idx < len(letter_labels):
                formatted_choices.append(f"{letter_labels[idx]}) {choice}")

        full_question = f"{puzzle}\n\n{question}\n\n" + "\n".join(formatted_choices)

        gold_letter = ""
        for idx, choice in enumerate(choices):
            if choice == answer_text and idx < len(letter_labels):
                gold_letter = letter_labels[idx]
                break

        examples.append(Example(id=str(i), question=full_question, gold_answer=gold_letter))
    return examples


def extract_answer_fallback(text: str) -> str:
    """Extract letter answer from a model response (any format)."""
    return _extract_letter(text)


# --- helpers ---

def _extract_letter(text: str, valid: str = "ABCDEF") -> str:
    """Extract a single letter from model output."""
    raw = text.strip()
    valid_set = set(valid)

    if raw.upper() in valid_set:
        return raw.upper()

    upper = raw.upper()

    for pattern in [
        r'\\boxed\{([' + valid + r'])',
        r'<answer>\s*([' + valid + r'])',
        r'"answer"\s*:\s*"([' + valid + r'])"',
    ]:
        matches = list(re.finditer(pattern, upper))
        if matches:
            return matches[-1].group(1)

    for pattern in [
        r"(?:THE\s+)?ANSWER\s*(?:IS\s*)?[:\s]*([" + valid + r"])\b",
        r"CORRECT\s+ANSWER\s*(?:IS\s*)?[:\s]*([" + valid + r"])\b",
        r"FINAL\s+ANSWER\s*[:\s]+([" + valid + r"])\b",
    ]:
        m = re.search(pattern, upper)
        if m:
            return m.group(1)

    m = re.search(r"\b([" + valid + r"])\s*[.!?)]*\s*$", upper)
    if m:
        return m.group(1)

    return ""
