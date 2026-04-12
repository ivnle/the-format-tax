#!/usr/bin/env python3
"""vLLM-hosted LLM judge for the public release."""

from __future__ import annotations

import argparse
import hashlib
import json
import re
from datetime import datetime, timezone
from pathlib import Path

from prompting import apply_chat_template


DEFAULT_JUDGE_MODEL = "Qwen/Qwen3-32B"
PROMPT_VERSION = "v4"
MAX_RESPONSE_CHARS = 8000
MAX_OUTPUT_TOKENS = 512


# Task-specific judge prompts. Each template must contain {question},
# {gold}, and {response} placeholders and end with a [[CORRECT]] /
# [[INCORRECT]] verdict instruction. Literal curly braces in the prose
# must be doubled ({{ }}) to escape str.format.
_MATH500_PROMPT = """\
You are judging a student's answer to a math problem.

Determine whether the student's final answer is mathematically equivalent to the gold answer. Focus only on the final answer, not the reasoning.

Equivalent means the same mathematical value. For example:
- 0.5 = 1/2
- 10% = 0.1
- {{1, -2}} = {{-2, 1}}  (order does not matter for unordered sets)
- (3, π/2) = (3, \\frac{{\\pi}}{{2}})  (LaTeX and plain-text forms are equivalent)

If the student did not provide a clear final answer, respond [[INCORRECT]].

<question>
{question}
</question>

<gold_answer>
{gold}
</gold_answer>

<student_response>
{response}
</student_response>

Respond with [[CORRECT]] if the student's final answer is mathematically equivalent to the gold answer, otherwise [[INCORRECT]]."""


_GPQA_PROMPT = """\
You are judging a student's answer to a multiple-choice science question.

The gold answer is a single letter (A, B, C, or D) that identifies the correct option in the question. Your task: determine whether the student picked the correct option.

### The rule

Your job is to figure out the student's **final committed answer** — their substantive conclusion after any self-corrections — and judge whether it matches the correct option.

Decision procedure:

1. **Track reversals.** Read through the full response. If the student explored multiple hypotheses and settled on one (e.g. "I thought Alice at first, but actually it's Peter"), their final commitment is the last one. Do not credit reasoning the student explicitly abandoned.
2. **Content beats letter.** When the student's final commitment expresses the correct option by content (option name, paraphrase, or value) but writes a contradictory letter at the end, trust the content. A wrong letter with correct content is a transcription slip and should not be penalized. Example: gold is B ("10^-4 eV"), the student's final reasoning says "therefore 10^-4 eV" but they write "Answer: C" at the end — this is [[CORRECT]]. The reasoning conclusion is what's being measured, not letter accuracy.
3. **Letter alone is enough.** If the student's final commitment is just a letter (no contradicting content), that letter is the answer.
4. **Content alone is enough.** If the student's final commitment is just content (no letter), that content is the answer.
5. **No clear commitment → [[INCORRECT]].** If the student trailed off, waffled without settling, or their final statement is genuinely ambiguous between options, the answer is [[INCORRECT]].

<question>
{question}
</question>

<gold_answer>
{gold}
</gold_answer>

<student_response>
{response}
</student_response>

Respond with [[CORRECT]] if the student's final committed answer matches the correct option, otherwise [[INCORRECT]]."""


_ZEBRALOGIC_PROMPT = """\
You are judging a student's answer to a logic puzzle presented as a multiple-choice question.

The gold answer is a single letter (A through F) that identifies the correct option in the question. Your task: determine whether the student picked the correct option.

### The rule

Your job is to figure out the student's **final committed answer** — their substantive conclusion after working through the puzzle — and judge whether it matches the correct option.

Decision procedure:

1. **Track reversals.** Logic puzzles often involve exploring multiple hypotheses. If the student explored several possibilities and settled on one (e.g. "I thought Peter at first, but actually it must be Alice"), their final commitment is the last one. Do not credit reasoning the student explicitly abandoned, and do not credit intermediate contradictions that they resolved later.
2. **Content beats letter.** When the student's final commitment expresses the correct option by content (a person's name, the object in question) but writes a contradictory letter at the end, trust the content. A wrong letter with correct content is a transcription slip and should not be penalized. Example: gold is D ("Peter"), the student's final reasoning concludes "therefore the person in House 1 is Peter" but they write "Answer: C" at the end — this is [[CORRECT]]. The reasoning conclusion is what's being measured, not letter accuracy.
3. **Letter alone is enough.** If the student's final commitment is just a letter (no contradicting content), that letter is the answer.
4. **Content alone is enough.** If the student's final commitment is just content (no letter), that content is the answer.
5. **No clear commitment → [[INCORRECT]].** If the student ran out of space mid-reasoning, waffled without settling, or their final statement is genuinely ambiguous between options, the answer is [[INCORRECT]].

<question>
{question}
</question>

<gold_answer>
{gold}
</gold_answer>

<student_response>
{response}
</student_response>

Respond with [[CORRECT]] if the student's final committed answer matches the correct option, otherwise [[INCORRECT]]."""


PROMPTS_BY_TASK: dict[str, str] = {
    "math500": _MATH500_PROMPT,
    "gpqa": _GPQA_PROMPT,
    "zebralogic": _ZEBRALOGIC_PROMPT,
}


def build_judge_prompt(*, task: str, question: str, gold: str, response: str) -> str:
    try:
        template = PROMPTS_BY_TASK[task]
    except KeyError as exc:
        raise ValueError(
            f"Unknown task {task!r}; expected one of {sorted(PROMPTS_BY_TASK)}"
        ) from exc
    return template.format(
        question=question,
        gold=gold,
        response=response[-MAX_RESPONSE_CHARS:],
    )


def parse_verdict(text: str) -> bool | None:
    match = re.search(r"\[\[(CORRECT|INCORRECT)\]\]", text, re.IGNORECASE)
    if match:
        return match.group(1).upper() == "CORRECT"
    return None


def default_cache_path() -> Path:
    return Path(__file__).resolve().parent / "results" / ".judge_cache.json"


def cache_key(
    *,
    task: str,
    question: str,
    gold: str,
    response: str,
    judge_model: str,
) -> str:
    digest = hashlib.sha256()
    for part in (task, question, gold, response, judge_model, PROMPT_VERSION):
        digest.update(part.encode("utf-8"))
        digest.update(b"\0")
    return digest.hexdigest()


def load_cache(path: Path) -> dict[str, bool | None]:
    if not path.exists():
        return {}
    with open(path, encoding="utf-8") as handle:
        return json.load(handle)


def save_cache(path: Path, cache: dict[str, bool | None]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with open(path, "w", encoding="utf-8") as handle:
        json.dump(cache, handle, indent=2, sort_keys=True)
        handle.write("\n")


def judge(
    records: list[dict],
    judge_model: str = DEFAULT_JUDGE_MODEL,
    cache_path: str | None = None,
    batch_size: int = 64,
    judge_tp: int = 2,
) -> list[dict]:
    cache_file = Path(cache_path) if cache_path else default_cache_path()
    cache = load_cache(cache_file)

    judged_records = [dict(record) for record in records]
    pending_metadata: list[tuple[int, str]] = []

    for index, record in enumerate(judged_records):
        key = cache_key(
            task=record["task"],
            question=record["question"],
            gold=record["gold"],
            response=record["raw_output"],
            judge_model=judge_model,
        )
        if key in cache:
            record["judge_correct"] = cache[key]
            continue

        pending_metadata.append((index, key))

    if not pending_metadata:
        return judged_records

    from vllm import LLM, SamplingParams

    llm = LLM(
        model=judge_model,
        tensor_parallel_size=judge_tp,
        trust_remote_code=True,
        max_model_len=16384,
    )
    tokenizer = llm.get_tokenizer()
    sampling_params = SamplingParams(
        temperature=0.0,
        top_p=1.0,
        max_tokens=MAX_OUTPUT_TOKENS,
    )

    pending_prompts = [
        apply_chat_template(
            tokenizer=tokenizer,
            prompt=build_judge_prompt(
                task=judged_records[index]["task"],
                question=judged_records[index]["question"],
                gold=judged_records[index]["gold"],
                response=judged_records[index]["raw_output"],
            ),
            model_name=judge_model,
            enable_thinking=False,
        )
        for index, _ in pending_metadata
    ]

    for start in range(0, len(pending_prompts), batch_size):
        batch_prompts = pending_prompts[start : start + batch_size]
        batch_metadata = pending_metadata[start : start + batch_size]
        outputs = llm.generate(batch_prompts, sampling_params)
        for (index, key), output in zip(batch_metadata, outputs):
            verdict = parse_verdict(output.outputs[0].text)
            cache[key] = verdict
            judged_records[index]["judge_correct"] = verdict

    save_cache(cache_file, cache)
    return judged_records


def summarize(records: list[dict]) -> list[dict]:
    grouped: dict[tuple[str, str, str], list[dict]] = {}
    for record in records:
        key = (record["task"], record["format"], record["decoding"])
        grouped.setdefault(key, []).append(record)

    summary = []
    for (task, format_name, decoding), group in sorted(grouped.items()):
        total = len(group)
        correct = sum(1 for record in group if record.get("judge_correct") is True)
        parse_failures = sum(1 for record in group if record.get("judge_correct") is None)
        summary.append(
            {
                "task": task,
                "format": format_name,
                "decoding": decoding,
                "correct": correct,
                "total": total,
                "parse_failures": parse_failures,
                "accuracy": (correct / total) if total else 0.0,
            }
        )
    return summary


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Judge worker for the format-tax release.")
    parser.add_argument("--input", required=True)
    parser.add_argument("--output", required=True)
    parser.add_argument("--judge-model", default=DEFAULT_JUDGE_MODEL)
    parser.add_argument("--judge-cache", default=str(default_cache_path()))
    parser.add_argument("--judge-tp", type=int, default=2)
    parser.add_argument("--batch-size", type=int, default=64)
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    input_path = Path(args.input)
    output_path = Path(args.output)
    output_path.parent.mkdir(parents=True, exist_ok=True)

    with open(input_path, encoding="utf-8") as handle:
        payload = json.load(handle)

    records = judge(
        payload["records"],
        judge_model=args.judge_model,
        cache_path=args.judge_cache,
        batch_size=args.batch_size,
        judge_tp=args.judge_tp,
    )
    payload["records"] = records
    payload["summary"] = summarize(records)
    payload["meta"]["judge_model"] = args.judge_model
    payload["meta"]["judge_tensor_parallel_size"] = args.judge_tp
    payload["meta"]["judge_cache"] = args.judge_cache
    payload["meta"]["judged_at"] = datetime.now(timezone.utc).isoformat()
    payload["meta"]["prompt_version"] = PROMPT_VERSION

    with open(output_path, "w", encoding="utf-8") as handle:
        json.dump(payload, handle, indent=2)
        handle.write("\n")


if __name__ == "__main__":
    main()
