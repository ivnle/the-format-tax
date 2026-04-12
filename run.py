#!/usr/bin/env python3
"""Orchestrate generation then judging as separate worker processes."""

from __future__ import annotations

import argparse
import json
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path

from tabulate import tabulate


DEFAULT_TASKS = ["math500"]
ALL_TASKS = ["math500", "gpqa", "zebralogic"]
ALL_FORMATS = ["freeform", "json", "xml", "latex", "markdown"]
ALL_DECODINGS = ["prompt", "gcd"]
DEFAULT_JUDGE_BACKENDS = ["vllm", "openai"]
DEFAULT_JUDGE_MODEL_VLLM = "Qwen/Qwen3-32B"
DEFAULT_JUDGE_MODEL_OPENAI = "gpt-5.4-nano"


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Public release runner for the format tax demo.")
    parser.add_argument("--model", default="Qwen/Qwen3-8B")
    parser.add_argument("--tasks", nargs="+", default=DEFAULT_TASKS, choices=ALL_TASKS)
    parser.add_argument("--formats", nargs="+", default=ALL_FORMATS, choices=ALL_FORMATS)
    parser.add_argument("--decoding", nargs="+", default=ALL_DECODINGS, choices=ALL_DECODINGS)
    parser.add_argument("--max-examples", type=int, default=None)
    parser.add_argument("--max-tokens", type=int, default=4096)
    parser.add_argument("--temperature", type=float, default=0.0)
    parser.add_argument("--tensor-parallel-size", type=int, default=1)
    parser.add_argument(
        "--judge-backend",
        choices=DEFAULT_JUDGE_BACKENDS,
        default="vllm",
        help="vllm: local Qwen3-32B (no API key, 2+ GPUs). openai: batch API (requires OPENAI_API_KEY, 50%% cheaper than standard API, completes within 24h).",
    )
    parser.add_argument(
        "--judge-model",
        default=None,
        help=(
            "Judge model id. Defaults depend on --judge-backend: "
            f"vllm -> {DEFAULT_JUDGE_MODEL_VLLM}, openai -> {DEFAULT_JUDGE_MODEL_OPENAI}."
        ),
    )
    parser.add_argument("--judge-tp", type=int, default=2, help="tensor-parallel size for --judge-backend vllm")
    parser.add_argument("--judge-cache", default=None, help="(vllm only) local sha256 verdict cache path")
    parser.add_argument("--judge-poll-interval", type=int, default=60, help="(openai only) batch poll interval in seconds")
    parser.add_argument("--enable-thinking", action="store_true")
    parser.add_argument("--output-dir", default="results")
    return parser.parse_args()


def extend_list_arg(command: list[str], flag: str, values: list[str]) -> None:
    command.append(flag)
    command.extend(values)


def slugify_model(model: str) -> str:
    return model.split("/")[-1].lower().replace(".", "-")


def print_summary(summary: list[dict]) -> None:
    headers = ["Task", "Format", "Decoding", "Accuracy", "Correct/Total", "Parse Failures"]
    rows = [
        [
            item["task"],
            item["format"],
            item["decoding"],
            f'{item["accuracy"]:.1%}',
            f'{item["correct"]}/{item["total"]}',
            item["parse_failures"],
        ]
        for item in summary
    ]
    print(tabulate(rows, headers=headers, tablefmt="simple"))


def _resolve_judge_model(args: argparse.Namespace) -> str:
    if args.judge_model is not None:
        return args.judge_model
    return (
        DEFAULT_JUDGE_MODEL_OPENAI
        if args.judge_backend == "openai"
        else DEFAULT_JUDGE_MODEL_VLLM
    )


def _build_judge_command(
    *,
    args: argparse.Namespace,
    release_dir: Path,
    raw_output_path: Path,
    final_output_path: Path,
    output_dir: Path,
    judge_model: str,
) -> list[str]:
    if args.judge_backend == "vllm":
        judge_cache = (
            Path(args.judge_cache)
            if args.judge_cache
            else output_dir / ".judge_cache.json"
        )
        return [
            sys.executable,
            str(release_dir / "judge.py"),
            "--input",
            str(raw_output_path),
            "--output",
            str(final_output_path),
            "--judge-model",
            judge_model,
            "--judge-cache",
            str(judge_cache),
            "--judge-tp",
            str(args.judge_tp),
        ]

    # openai batch backend
    state_path = raw_output_path.with_suffix(".openai.state.json")
    return [
        sys.executable,
        str(release_dir / "judge_openai.py"),
        "run",
        "--input",
        str(raw_output_path),
        "--output",
        str(final_output_path),
        "--state",
        str(state_path),
        "--judge-model",
        judge_model,
        "--interval",
        str(args.judge_poll_interval),
    ]


def main() -> None:
    args = parse_args()
    release_dir = Path(__file__).resolve().parent
    output_dir = (release_dir / args.output_dir).resolve()
    output_dir.mkdir(parents=True, exist_ok=True)

    timestamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    base_name = f"{slugify_model(args.model)}_{timestamp}"
    raw_output_path = output_dir / f"{base_name}.raw.json"
    final_output_path = output_dir / f"{base_name}.json"

    judge_model = _resolve_judge_model(args)

    generate_cmd = [sys.executable, str(release_dir / "generate.py")]
    extend_list_arg(generate_cmd, "--tasks", args.tasks)
    extend_list_arg(generate_cmd, "--formats", args.formats)
    extend_list_arg(generate_cmd, "--decoding", args.decoding)
    generate_cmd.extend(
        [
            "--model",
            args.model,
            "--max-tokens",
            str(args.max_tokens),
            "--temperature",
            str(args.temperature),
            "--tensor-parallel-size",
            str(args.tensor_parallel_size),
            "--output",
            str(raw_output_path),
        ]
    )
    if args.max_examples is not None:
        generate_cmd.extend(["--max-examples", str(args.max_examples)])
    if args.enable_thinking:
        generate_cmd.append("--enable-thinking")

    judge_cmd = _build_judge_command(
        args=args,
        release_dir=release_dir,
        raw_output_path=raw_output_path,
        final_output_path=final_output_path,
        output_dir=output_dir,
        judge_model=judge_model,
    )

    subprocess.run(generate_cmd, cwd=release_dir, check=True)
    subprocess.run(judge_cmd, cwd=release_dir, check=True)

    with open(final_output_path, encoding="utf-8") as handle:
        payload = json.load(handle)

    print_summary(payload.get("summary", []))
    print(f"\nRaw generations: {raw_output_path}")
    print(f"Final results:   {final_output_path}")
    print(f"Judge backend:   {args.judge_backend} ({judge_model})")


if __name__ == "__main__":
    main()
