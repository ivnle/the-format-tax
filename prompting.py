"""Shared prompt rendering and chat-template helpers for the public release."""

from __future__ import annotations

import inspect
from functools import lru_cache
from pathlib import Path

from jinja2 import Environment, FileSystemLoader


PROMPT_TEMPLATES_DIR = Path(__file__).resolve().parent / "prompt_templates"
EXAMPLES_DIR = PROMPT_TEMPLATES_DIR / "examples"

_TASK_TEMPLATE_BY_NAME = {
    "math500": "tasks/math500.j2",
    "gpqa": "tasks/gpqa.j2",
    "zebralogic": "tasks/zebralogic.j2",
}

_TASK_NAME_BY_INSTRUCTION = {
    "Solve the following math problem.": "math500",
    "Answer the following graduate-level science question.": "gpqa",
    "Answer the following multiple-choice question.": "gpqa",
    "Solve the following logic puzzle.": "zebralogic",
}


@lru_cache(maxsize=1)
def _environment() -> Environment:
    return Environment(
        loader=FileSystemLoader(str(PROMPT_TEMPLATES_DIR)),
        trim_blocks=True,
        lstrip_blocks=True,
    )


def resolve_task_name(task_instruction: str) -> str:
    """Infer the public task name from the task instruction text."""
    task_name = _TASK_NAME_BY_INSTRUCTION.get(task_instruction.strip())
    if task_name:
        return task_name

    normalized = task_instruction.strip().lower()
    if "math" in normalized:
        return "math500"
    if "science" in normalized or "multiple-choice" in normalized:
        return "gpqa"
    if "logic puzzle" in normalized:
        return "zebralogic"
    raise ValueError(f"Unable to infer task from instruction: {task_instruction!r}")


@lru_cache(maxsize=32)
def _load_example(task_name: str, format_name: str) -> str:
    """Load the few-shot example text for a (task, structured_format) pair."""
    path = EXAMPLES_DIR / task_name / f"{format_name}.txt"
    return path.read_text(encoding="utf-8").rstrip("\n")


def render_prompt(
    *,
    task_instruction: str,
    question: str,
    format_name: str,
    schema: dict | None = None,
    grammar: str | None = None,
) -> str:
    """Render a task prompt using the vendored source templates.

    Freeform renders with no format hint at all (show_freeform_hint=False,
    no closing, no few-shot example). The LLM judge handles answer
    extraction regardless of how the model phrases its response, so the
    baseline stays uncontaminated by any formatting instruction.

    Structured formats (json/xml/latex/markdown) render with one
    vendored few-shot example loaded from
    ``prompt_templates/examples/<task>/<format>.txt``. The example shows
    one valid instance of the grammar/schema on a simple unrelated
    problem so the model sees both the declared structure and a
    concrete form of it.
    """
    task_name = resolve_task_name(task_instruction)
    template = _environment().get_template(_TASK_TEMPLATE_BY_NAME[task_name])

    context = {
        "question": question,
        "is_freeform": format_name == "freeform",
        "has_format_instructions": schema is not None or grammar is not None,
        "show_freeform_hint": False,
    }
    if schema is not None:
        import json

        context.update(
            {
                "schema_type": "json",
                "schema": json.dumps(schema, indent=2),
                "format_name": "json",
                "format_type": "json",
                "examples": [_load_example(task_name, format_name)],
            }
        )
    elif grammar is not None:
        context.update(
            {
                "schema_type": "lark",
                "grammar": grammar,
                "format_name": format_name.upper(),
                "format_type": format_name,
                "examples": [_load_example(task_name, format_name)],
            }
        )

    return template.render(**context).strip()


def _infer_model_family(model_name: str) -> str | None:
    normalized = model_name.strip().lower()
    if "qwen3" in normalized:
        return "qwen3"
    if "smollm3" in normalized:
        return "smollm3"
    if "olmo-3" in normalized or "olmo3" in normalized:
        return "olmo3"
    if "nemotron" in normalized:
        return "nemotron"
    if "gpt-oss" in normalized or "gpt_oss" in normalized:
        return "gpt_oss"
    return None


def reasoning_parser_for_model(model_name: str, enable_thinking: bool) -> str | None:
    """Return the vLLM reasoning parser for supported thinking-enabled families."""
    if not enable_thinking:
        return None

    family = _infer_model_family(model_name)
    if family in {"qwen3", "smollm3"}:
        return "qwen3"
    if family == "olmo3":
        return "olmo3"
    if family == "nemotron":
        return "nemotron"
    raise ValueError(
        f"--enable-thinking is only supported for known model families "
        f"(Qwen3, SmolLM3, OLMo 3, Nemotron). Got: {model_name!r}"
    )


@lru_cache(maxsize=1)
def _guidance_fail_fast_mode() -> str:
    """Validate how the pinned vLLM build enforces fail-fast structured outputs."""
    from vllm.config import StructuredOutputsConfig
    from vllm.sampling_params import SamplingParams, StructuredOutputsParams

    signature = inspect.signature(StructuredOutputsConfig)
    if "disable_fallback" in signature.parameters:
        return "native-disable-fallback"

    config = StructuredOutputsConfig(backend="guidance")
    params = SamplingParams(
        temperature=0.0,
        max_tokens=1,
        structured_outputs=StructuredOutputsParams(grammar='start: "x"'),
    )
    params._validate_structured_outputs(config, tokenizer=object())
    if params.structured_outputs._backend != "guidance":
        raise RuntimeError(
            "The installed vLLM build does not preserve an explicit "
            "guidance backend selection for structured outputs."
        )
    return "explicit-guidance-backend"


def structured_outputs_config(model_name: str, enable_thinking: bool) -> dict:
    """Build the vLLM structured outputs config for the release worker."""
    config = {
        "backend": "guidance",
    }
    if _guidance_fail_fast_mode() == "native-disable-fallback":
        config["disable_fallback"] = True
    parser = reasoning_parser_for_model(model_name, enable_thinking)
    if parser is not None:
        config["reasoning_parser"] = parser
    return config


def apply_chat_template(
    *,
    tokenizer,
    prompt: str,
    model_name: str,
    enable_thinking: bool,
) -> str:
    """Mirror the source vLLM chat-template flow used for generation.

    Model families with a configurable reasoning/thinking mode are pinned
    to NO reasoning, so every model in the sweep produces a direct
    response with no chain-of-thought scratchpad:

    - qwen3 / smollm3 / nemotron: pass `enable_thinking=False` kwarg,
      which their chat templates interpret correctly.
    - gpt_oss (harmony chat format): `reasoning_effort` is passed as a
      template kwarg, and the assistant generation prefix is forced to
      start in the `final` channel (`<|channel|>final<|message|>`) so
      the model skips the analysis channel entirely. Both the
      reasoning_effort kwarg and the forced-final prefix are applied
      defensively — either alone would give no analysis, and together
      they give no analysis even if the model gets confused about one.
    """
    family = _infer_model_family(model_name)
    messages = [{"role": "user", "content": prompt}]

    if family == "gpt_oss":
        rendered = tokenizer.apply_chat_template(
            messages,
            add_generation_prompt=True,
            tokenize=False,
            reasoning_effort="low",
        )
        # Force the model into the final channel so it emits its response
        # directly without an analysis/reasoning phase.
        return rendered + "<|channel|>final<|message|>"

    if family in {"qwen3", "smollm3", "nemotron"}:
        try:
            return tokenizer.apply_chat_template(
                messages,
                enable_thinking=enable_thinking,
                add_generation_prompt=True,
                tokenize=False,
            )
        except TypeError as exc:
            raise RuntimeError(
                f"Tokenizer for {model_name!r} does not support "
                "enable_thinking in apply_chat_template()."
            ) from exc

    if enable_thinking and family is None:
        raise ValueError(
            f"Cannot safely enable thinking for unknown model family: {model_name!r}"
        )

    return tokenizer.apply_chat_template(
        messages,
        add_generation_prompt=True,
        tokenize=False,
    )
