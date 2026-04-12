#!/usr/bin/env python3
"""Generation worker for the public release."""

from __future__ import annotations

import argparse
import json
from datetime import datetime, timezone
from pathlib import Path

from formats import FORMATS
from prompting import apply_chat_template, structured_outputs_config
from tasks import TASKS


DEFAULT_TASKS = ["math500"]
ALL_TASKS = ["math500", "gpqa", "zebralogic"]
ALL_FORMATS = ["freeform", "json", "xml", "latex", "markdown"]
ALL_DECODINGS = ["prompt", "gcd"]


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Generation worker for the format-tax release.")
    parser.add_argument("--model", default="Qwen/Qwen3-8B")
    parser.add_argument("--tasks", nargs="+", default=DEFAULT_TASKS, choices=ALL_TASKS)
    parser.add_argument("--formats", nargs="+", default=ALL_FORMATS, choices=ALL_FORMATS)
    parser.add_argument("--decoding", nargs="+", default=ALL_DECODINGS, choices=ALL_DECODINGS)
    parser.add_argument("--max-examples", type=int, default=None)
    parser.add_argument("--max-tokens", type=int, default=4096)
    parser.add_argument("--temperature", type=float, default=0.0)
    parser.add_argument("--tensor-parallel-size", type=int, default=1)
    parser.add_argument("--max-model-len", type=int, default=8192)
    parser.add_argument("--enable-thinking", action="store_true")
    parser.add_argument("--output", required=True)
    return parser.parse_args()


def iter_conditions(tasks: list[str], formats: list[str], decodings: list[str]):
    for task_name in tasks:
        for format_name in formats:
            for decoding in decodings:
                if format_name == "freeform" and decoding == "gcd":
                    continue
                yield task_name, format_name, decoding


def main() -> None:
    args = parse_args()

    from vllm import LLM, SamplingParams
    from vllm.sampling_params import StructuredOutputsParams

    output_path = Path(args.output)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    # Streaming sidecar: each record is flushed to disk as it is produced.
    # Lets an operator (or another process) tail the file mid-run to verify
    # generation quality, and makes the run resumable-by-hand if the process
    # dies before the final .raw.json atomic write below.
    jsonl_path = output_path.with_suffix(output_path.suffix + ".jsonl")
    # Truncate any partial file from a prior crashed run.
    jsonl_path.write_text("", encoding="utf-8")

    llm = LLM(
        model=args.model,
        tensor_parallel_size=args.tensor_parallel_size,
        trust_remote_code=True,
        max_model_len=args.max_model_len,
        structured_outputs_config=structured_outputs_config(
            args.model,
            args.enable_thinking,
        ),
    )
    tokenizer = llm.get_tokenizer()

    task_examples = {
        task_name: TASKS[task_name].load_examples(max_examples=args.max_examples)
        for task_name in args.tasks
    }

    records: list[dict] = []
    with open(jsonl_path, "a", encoding="utf-8") as jsonl_handle:
        for task_name, format_name, decoding in iter_conditions(
            args.tasks,
            args.formats,
            args.decoding,
        ):
            task_module = TASKS[task_name]
            format_module = FORMATS[format_name]
            examples = task_examples[task_name]

            prompts = [
                format_module.wrap_prompt(task_module.INSTRUCTION, example.question)
                for example in examples
            ]
            formatted_prompts = [
                apply_chat_template(
                    tokenizer=tokenizer,
                    prompt=prompt,
                    model_name=args.model,
                    enable_thinking=args.enable_thinking,
                )
                for prompt in prompts
            ]

            structured_outputs = None
            if decoding == "gcd":
                grammar = format_module.load_grammar(task_name)
                if isinstance(grammar, dict):
                    structured_outputs = StructuredOutputsParams(json=grammar)
                else:
                    structured_outputs = StructuredOutputsParams(grammar=grammar)

            sampling_params = SamplingParams(
                temperature=args.temperature,
                top_p=1.0,
                max_tokens=args.max_tokens,
                structured_outputs=structured_outputs,
                extra_args={"enable_thinking": args.enable_thinking},
            )

            outputs = llm.generate(formatted_prompts, sampling_params)
            for example, prompt, output in zip(examples, prompts, outputs):
                raw_output = output.outputs[0].text
                record = {
                    "example_id": example.id,
                    "task": task_name,
                    "format": format_name,
                    "decoding": decoding,
                    "question": example.question,
                    "prompt": prompt,
                    "gold": example.gold_answer,
                    "raw_output": raw_output,
                    "extracted_answer": format_module.extract_answer(
                        raw_output,
                        task_module.extract_answer_fallback,
                    ),
                    "output_tokens": len(output.outputs[0].token_ids or []),
                }
                records.append(record)
                jsonl_handle.write(json.dumps(record) + "\n")
            jsonl_handle.flush()

    payload = {
        "meta": {
            "model": args.model,
            "tensor_parallel_size": args.tensor_parallel_size,
            "enable_thinking": args.enable_thinking,
            "temperature": args.temperature,
            "max_tokens": args.max_tokens,
            "max_model_len": args.max_model_len,
            "tasks": args.tasks,
            "formats": args.formats,
            "decoding": args.decoding,
            "max_examples": args.max_examples,
            "generated_at": datetime.now(timezone.utc).isoformat(),
        },
        "records": records,
    }

    with open(output_path, "w", encoding="utf-8") as handle:
        json.dump(payload, handle, indent=2)
        handle.write("\n")


if __name__ == "__main__":
    main()
