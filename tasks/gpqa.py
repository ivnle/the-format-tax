"""GPQA task metadata and fallback extraction."""

import hashlib
import random
import re
from dataclasses import dataclass
from typing import Optional

from datasets import load_dataset
from datasets.exceptions import DatasetNotFoundError


NAME = "gpqa"
INSTRUCTION = "Answer the following multiple-choice question."


@dataclass
class Example:
    id: str
    question: str  # includes formatted choices
    gold_answer: str  # letter A-D


def load_examples(max_examples: Optional[int] = None) -> list[Example]:
    """Load GPQA Diamond from HuggingFace (Idavidrein/gpqa, gpqa_diamond split)."""
    try:
        ds = load_dataset("Idavidrein/gpqa", "gpqa_diamond", split="train")
    except DatasetNotFoundError as exc:
        raise RuntimeError(
            "GPQA-Diamond is gated on Hugging Face. Request dataset access on "
            "the Hub and set HF_TOKEN before running `--tasks gpqa`."
        ) from exc
    examples = []
    for i, item in enumerate(ds):
        if max_examples is not None and i >= max_examples:
            break
        question, gold_letter = _format_item(item)
        examples.append(Example(id=str(i), question=question, gold_answer=gold_letter))
    return examples


def extract_answer_fallback(text: str) -> str:
    """Extract letter answer from a model response (any format)."""
    return _extract_letter(text, valid="ABCD")


# --- helpers ---

def _format_item(item: dict) -> tuple[str, str]:
    """Format a GPQA item into (question_text, gold_letter)."""
    question = item.get("Question", "").strip()

    if "choice_A" in item:
        choices = [
            ("A", item["choice_A"]),
            ("B", item["choice_B"]),
            ("C", item["choice_C"]),
            ("D", item["choice_D"]),
        ]
        gold_letter = item.get("Answer Key", "A")
    else:
        correct = item.get("Correct Answer", "")
        others = [
            item.get("Incorrect Answer 1", ""),
            item.get("Incorrect Answer 2", ""),
            item.get("Incorrect Answer 3", ""),
        ]
        all_choices = [correct] + others
        seed_str = str(item.get("Record ID", "") or question)
        seed = int(hashlib.sha256(seed_str.encode()).hexdigest(), 16) % (2**32)
        rng = random.Random(seed)
        rng.shuffle(all_choices)
        choices = [(chr(65 + i), text) for i, text in enumerate(all_choices)]
        gold_letter = "A"
        for letter, text in choices:
            if text == correct:
                gold_letter = letter
                break

    formatted = question + "\n\n"
    for letter, text in choices:
        formatted += f"{letter}) {text.strip()}\n"
    return formatted.strip(), gold_letter


def _extract_letter(text: str, valid: str = "ABCD") -> str:
    """Extract a single letter from model output using multiple patterns."""
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
