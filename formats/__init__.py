"""Format modules for the format-tax demo.

Each format module exposes a uniform interface:

  NAME: str
  wrap_prompt(task_instruction: str, question: str) -> str
  extract_answer(raw_output: str, task_fallback_extractor=None) -> str
  load_grammar(task_name: str) -> str | dict | None

Structured formats load their source-faithful schema/grammar from
`grammars/<task>/` and inject it into the prompt. Freeform asks no
format at all: the LLM judge handles answer extraction regardless of
how the model phrases its response, so the baseline stays uncontaminated
by any formatting hint.
"""

from . import freeform, json, xml, latex, markdown

FORMATS = {
    freeform.NAME: freeform,
    json.NAME: json,
    xml.NAME: xml,
    latex.NAME: latex,
    markdown.NAME: markdown,
}

__all__ = ["FORMATS", "freeform", "json", "xml", "latex", "markdown"]
