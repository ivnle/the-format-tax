"""Inspect a (freeform, structured-prompt, structured-gcd) triple for a
single example, for a single model.

Usage:
    python dev/show_triple.py --split <split> --task <task> --format <format> \\
        [--example-id <id>] [--random] [--where <filter>] [--full-output]

Pulls data from the HF dataset ivnle/the-format-tax.

Examples:
    # Random gpt-oss math500 json triple
    python dev/show_triple.py --split gpt_oss_20b --task math500 --format json --random

    # Specific example
    python dev/show_triple.py --split gpt_oss_20b --task math500 --format json \\
        --example-id 42

    # Random case where freeform was correct but structured was wrong
    python dev/show_triple.py --split gpt_oss_20b --task math500 --format json \\
        --random --where "ff_correct and not gcd_correct"

Supported --where expressions:
    ff_correct, prompt_correct, gcd_correct    (bool per cell)
    ff_parsed, prompt_parsed, gcd_parsed       (bool per cell, excludes judge parse failures)

Output: prints a structured dump showing the question, gold answer, and for
each of the three cells:
    - the full prompt actually sent to the model (so you can see the format
      instructions + schema + few-shot)
    - the model's raw_output (truncated to 800 chars by default; full with
      --full-output)
    - the format module's extracted_answer
    - the judge's verdict

Also prints a 'thinking leak check' for the three raw_outputs that flags
any occurrence of analysis, <|channel|>, <think>, etc.
"""

from __future__ import annotations

import argparse
import os
import random
import re
import sys
from typing import Any

from datasets import load_dataset

DATASET = "ivnle/the-format-tax"


THINKING_PATTERNS = [
    (r"^analysis(?!ing)", "starts with 'analysis'"),
    (r"assistantfinal", "contains 'assistantfinal'"),
    (r"<\|channel\|>", "contains '<|channel|>'"),
    (r"<\|thinking\|>", "contains '<|thinking|>'"),
    (r"<think>", "contains '<think>'"),
    (r"</think>", "contains '</think>'"),
    (r"<thought>", "contains '<thought>'"),
]


def thinking_leak_report(raw_output: str) -> list[str]:
    hits = []
    for pat, label in THINKING_PATTERNS:
        if re.search(pat, raw_output):
            hits.append(label)
    return hits


def truncate(s: str, n: int) -> str:
    if len(s) <= n:
        return s
    return s[:n] + f"\n... [truncated, {len(s) - n} chars omitted]"


def load_split(split: str):
    return load_dataset(DATASET, split=split)


def index_triples(ds, task: str, fmt: str) -> dict[str, dict[str, dict]]:
    """Return {example_id: {"freeform": rec, "prompt": rec, "gcd": rec}}.
    Only includes example_ids that have all three cells for this (task, fmt).
    """
    tasks = ds["task"]
    fmts = ds["format"]
    decs = ds["decoding"]
    eids = ds["example_id"]
    records_idx = {}
    for i in range(len(ds)):
        if tasks[i] != task:
            continue
        if fmts[i] == "freeform":
            if decs[i] != "prompt":
                continue
            records_idx.setdefault(eids[i], {})["freeform"] = i
        elif fmts[i] == fmt:
            if decs[i] == "prompt":
                records_idx.setdefault(eids[i], {})["prompt"] = i
            elif decs[i] == "gcd":
                records_idx.setdefault(eids[i], {})["gcd"] = i
    # Keep only complete triples
    complete = {
        eid: idx_map
        for eid, idx_map in records_idx.items()
        if {"freeform", "prompt", "gcd"} <= set(idx_map.keys())
    }
    return complete


def get_triple(ds, idx_map: dict[str, int]) -> dict[str, dict]:
    return {
        "freeform": ds[idx_map["freeform"]],
        "prompt": ds[idx_map["prompt"]],
        "gcd": ds[idx_map["gcd"]],
    }


def eval_where_filter(expr: str, triple: dict[str, dict]) -> bool:
    env = {
        "ff_correct": triple["freeform"]["judge_correct"],
        "ff_parsed": triple["freeform"]["judge_parsed"],
        "prompt_correct": triple["prompt"]["judge_correct"],
        "prompt_parsed": triple["prompt"]["judge_parsed"],
        "gcd_correct": triple["gcd"]["judge_correct"],
        "gcd_parsed": triple["gcd"]["judge_parsed"],
    }
    try:
        return bool(eval(expr, {"__builtins__": {}}, env))
    except Exception as e:
        raise SystemExit(f"--where expression failed: {e}")


def print_cell(label: str, cell: dict, full_output: bool) -> None:
    print()
    print("=" * 76)
    print(f"{label}  |  format={cell['format']}  decoding={cell['decoding']}")
    print("=" * 76)
    print(f"judge_correct: {cell['judge_correct']}  (parsed={cell['judge_parsed']})")
    print(f"extracted_answer: {cell['extracted_answer']!r}")
    print()
    print("--- PROMPT (what the model saw) ---")
    p = cell["prompt"]
    print(truncate(p, 2500) if not full_output else p)
    print()
    print("--- RAW OUTPUT ---")
    r = cell["raw_output"]
    print(truncate(r, 2000) if not full_output else r)

    hits = thinking_leak_report(r)
    if hits:
        print()
        print(f"  ⚠ THINKING LEAK: {', '.join(hits)}")


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--split", required=True, help="HF dataset split (model name)")
    ap.add_argument("--task", required=True, choices=["math500", "gpqa", "zebralogic"])
    ap.add_argument("--format", required=True, choices=["json", "xml", "latex", "markdown"])
    ap.add_argument("--example-id", help="specific example_id to look up")
    ap.add_argument("--random", action="store_true", help="pick a random matching example")
    ap.add_argument("--where", help="boolean filter over (ff/prompt/gcd)_(correct/parsed)")
    ap.add_argument("--full-output", action="store_true", help="don't truncate prompts/outputs")
    ap.add_argument("--count", type=int, default=1, help="how many triples to show")
    args = ap.parse_args()

    ds = load_split(args.split)
    triples_idx = index_triples(ds, args.task, args.format)
    if not triples_idx:
        print(f"no triples found for task={args.task} format={args.format}")
        sys.exit(1)

    candidates = sorted(triples_idx.keys(), key=lambda s: int(s) if s.isdigit() else s)

    if args.example_id is not None:
        if args.example_id not in triples_idx:
            raise SystemExit(f"example_id {args.example_id!r} not found")
        picks = [args.example_id]
    else:
        # Apply where filter if given
        if args.where:
            filtered = []
            for eid in candidates:
                triple = get_triple(ds, triples_idx[eid])
                if eval_where_filter(args.where, triple):
                    filtered.append(eid)
            candidates = filtered
            if not candidates:
                raise SystemExit(f"no examples match --where {args.where!r}")

        if args.random:
            picks = random.sample(candidates, min(args.count, len(candidates)))
        else:
            picks = candidates[: args.count]

    for eid in picks:
        triple = get_triple(ds, triples_idx[eid])
        ff = triple["freeform"]
        print()
        print("#" * 76)
        print(f"# split={args.split}  task={args.task}  format={args.format}")
        print(f"# example_id={eid}")
        print("#" * 76)
        print()
        print(f"QUESTION: {truncate(ff['question'], 1000) if not args.full_output else ff['question']}")
        print()
        print(f"GOLD: {ff['gold']!r}")

        summary = (
            f"  freeform.prompt: {triple['freeform']['judge_correct']!s:>5} "
            f"(parsed={triple['freeform']['judge_parsed']})\n"
            f"  {args.format}.prompt:  {triple['prompt']['judge_correct']!s:>5} "
            f"(parsed={triple['prompt']['judge_parsed']})\n"
            f"  {args.format}.gcd:     {triple['gcd']['judge_correct']!s:>5} "
            f"(parsed={triple['gcd']['judge_parsed']})"
        )
        print()
        print("JUDGE VERDICTS:")
        print(summary)

        print_cell("FREEFORM", triple["freeform"], args.full_output)
        print_cell(f"{args.format.upper()} + PROMPT", triple["prompt"], args.full_output)
        print_cell(f"{args.format.upper()} + GCD", triple["gcd"], args.full_output)
        print()


if __name__ == "__main__":
    main()
