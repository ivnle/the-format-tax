#!/usr/bin/env python3
"""Verify a shipped reference artifact actually demonstrates the headline claim.

The public release promises two effects in README / spec:
  1. Prompt-only structuring drops accuracy vs the freeform baseline.
  2. Grammar-constrained decoding (GCD) drops accuracy vs the freeform baseline.

This script takes a judged results JSON (as produced by `python run.py`) and
asserts that the artifact contains concrete evidence for both. A future
reference artifact where, e.g., every GCD cell tied or beat freeform would
fail this gate instead of silently shipping a weaker demo than we claim.

Gate:
  * Zero judge parse failures across the artifact.
  * At least one (format != freeform, decoding == prompt) cell below the
    freeform baseline for its task.
  * At least one (format != freeform, decoding == gcd) cell below the
    freeform baseline for its task.

Self-contained: only depends on stdlib. Safe to ship to the public repo.
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path


def _index_summary(summary: list[dict]) -> dict[tuple[str, str, str], dict]:
    return {(row["task"], row["format"], row["decoding"]): row for row in summary}


def check(summary: list[dict]) -> list[str]:
    failures: list[str] = []
    by_cell = _index_summary(summary)

    tasks = sorted({row["task"] for row in summary})
    if not tasks:
        return ["Summary contains no rows."]

    freeform_accuracy: dict[str, float] = {}
    for task in tasks:
        freeform = by_cell.get((task, "freeform", "prompt"))
        if freeform is None:
            failures.append(f"No freeform/prompt baseline for task {task!r}.")
            continue
        freeform_accuracy[task] = freeform["accuracy"]

    total_parse_failures = sum(row.get("parse_failures", 0) for row in summary)
    if total_parse_failures:
        failures.append(
            f"Expected zero parse failures across the artifact, found {total_parse_failures}."
        )

    prompt_drops: list[str] = []
    gcd_drops: list[str] = []
    for row in summary:
        if row["format"] == "freeform":
            continue
        baseline = freeform_accuracy.get(row["task"])
        if baseline is None:
            continue
        if row["accuracy"] >= baseline:
            continue
        label = f'{row["task"]}/{row["format"]}:{row["accuracy"]:.1%}<{baseline:.1%}'
        if row["decoding"] == "prompt":
            prompt_drops.append(label)
        elif row["decoding"] == "gcd":
            gcd_drops.append(label)

    if not prompt_drops:
        failures.append(
            "No prompt-only structured format dropped below its freeform baseline. "
            "The artifact does not demonstrate the prompt-only half of the claim."
        )
    if not gcd_drops:
        failures.append(
            "No GCD structured format dropped below its freeform baseline. "
            "The artifact does not demonstrate the GCD half of the claim."
        )

    if not failures:
        print(f"Tasks present: {tasks}")
        print(f"Freeform baselines: {freeform_accuracy}")
        print(f"Prompt-only drops: {prompt_drops}")
        print(f"GCD drops: {gcd_drops}")
        print("Reference contract holds.")

    return failures


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Check that a reference artifact demonstrates both halves of the headline claim."
    )
    parser.add_argument("--input", required=True, help="Path to a judged results JSON file.")
    args = parser.parse_args()

    with open(Path(args.input), encoding="utf-8") as handle:
        payload = json.load(handle)

    failures = check(payload.get("summary", []))
    if failures:
        for failure in failures:
            print(f"FAIL: {failure}", file=sys.stderr)
        raise SystemExit(1)


if __name__ == "__main__":
    main()
