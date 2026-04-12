"""Task modules for the format tax demo.

Each module exposes:
  INSTRUCTION: str           # short task instruction (e.g., "Solve the following math problem.")
  Example                    # dataclass with id, question, gold_answer
  load_examples(max_examples) -> list[Example]
  extract_answer_fallback(text) -> str  # last-resort extraction, used by formats
"""

from . import math500, gpqa, zebralogic

TASKS = {
    "math500": math500,
    "gpqa": gpqa,
    "zebralogic": zebralogic,
}
