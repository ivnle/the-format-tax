#!/usr/bin/env python3
"""OpenAI batch-API judge for the public release.

An alternative to the local vLLM judge (`judge.py`). Instead of loading
Qwen3-32B on a GPU, this submits the judge prompts to OpenAI's batch
API — 50% cheaper than standard completions, same verdict quality for
the three demo tasks.

Three subcommands:

  submit    build prompts, upload a JSONL file, create a batch job,
            save a state file with batch_id + custom_id→index mapping
  poll      check batch status; either poll until done or `--once`
  retrieve  download batch output, parse verdicts, apply to records,
            write the final judged .json
  run       chain submit → poll → retrieve (one command, blocks until
            done)

All four subcommands share the same task-specific prompt templates as
the vLLM judge (`PROMPTS_BY_TASK` in `judge.py`). The task routing,
response truncation, and verdict regex are identical.

Usage (detached workflow):
  python judge_openai.py submit --input r.json --state s.json
  # …later…
  python judge_openai.py poll --state s.json
  python judge_openai.py retrieve --state s.json --input r.json --output o.json

Usage (blocking workflow):
  python judge_openai.py run --input r.json --output o.json --state s.json

Requires `OPENAI_API_KEY` in the environment.
"""

from __future__ import annotations

import argparse
import json
import sys
import time
from datetime import datetime, timezone
from pathlib import Path

# Reuse the prompt registry, verdict regex, and summary aggregator from
# the vLLM judge. One source of truth for the judge's scientific content.
from judge import (
    PROMPT_VERSION,
    build_judge_prompt,
    parse_verdict,
    summarize,
)


DEFAULT_JUDGE_MODEL = "gpt-5.4-nano"
DEFAULT_MAX_OUTPUT_TOKENS = 512
DEFAULT_POLL_INTERVAL = 60
DEFAULT_COMPLETION_WINDOW = "24h"


# ---------------------------------------------------------------------------
# Pure builders (tested directly)
# ---------------------------------------------------------------------------


def build_batch_request(
    *,
    custom_id: str,
    judge_model: str,
    task: str,
    question: str,
    gold: str,
    response: str,
    max_tokens: int = DEFAULT_MAX_OUTPUT_TOKENS,
) -> dict:
    """Build one line of the OpenAI batch-API input JSONL.

    Each record becomes a POST to /v1/chat/completions with the
    task-specific judge prompt as the user message. Temperature is
    pinned to 0 for deterministic verdicts.
    """
    prompt = build_judge_prompt(
        task=task,
        question=question,
        gold=gold,
        response=response,
    )
    body = {
        "model": judge_model,
        "messages": [{"role": "user", "content": prompt}],
        "max_completion_tokens": max_tokens,
        "temperature": 0.0,
    }
    return {
        "custom_id": custom_id,
        "method": "POST",
        "url": "/v1/chat/completions",
        "body": body,
    }


def parse_batch_result_line(line: str) -> tuple[str, bool | None]:
    """Parse one line from the batch-API output JSONL.

    Returns `(custom_id, verdict)` where verdict is True, False, or
    None. None covers any non-200 response, empty body, missing
    message content, or unparseable verdict token — the retrieve step
    treats these as parse failures in the final summary.
    """
    result = json.loads(line)
    custom_id = result.get("custom_id", "")

    response = result.get("response")
    if not response:
        return custom_id, None
    if response.get("status_code") != 200:
        return custom_id, None

    body = response.get("body") or {}
    choices = body.get("choices") or []
    if not choices:
        return custom_id, None

    message = choices[0].get("message") or {}
    content = message.get("content") or ""
    if not content:
        return custom_id, None

    return custom_id, parse_verdict(content)


# ---------------------------------------------------------------------------
# State file (batch_id + custom_id→record index mapping)
# ---------------------------------------------------------------------------


def save_state(path: Path, state: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with open(path, "w", encoding="utf-8") as handle:
        json.dump(state, handle, indent=2, sort_keys=True)
        handle.write("\n")


def load_state(path: Path) -> dict:
    with open(path, encoding="utf-8") as handle:
        return json.load(handle)


# ---------------------------------------------------------------------------
# OpenAI client (mocked in tests)
# ---------------------------------------------------------------------------


def _openai_client():
    """Construct an OpenAI client; isolated for test mocking."""
    from openai import OpenAI

    return OpenAI()


# ---------------------------------------------------------------------------
# Subcommand handlers
# ---------------------------------------------------------------------------


def cmd_submit(args: argparse.Namespace) -> int:
    input_path = Path(args.input)
    state_path = Path(args.state)
    judge_model = args.judge_model
    max_tokens = getattr(args, "max_tokens", DEFAULT_MAX_OUTPUT_TOKENS)

    with open(input_path, encoding="utf-8") as handle:
        payload = json.load(handle)
    records = payload["records"]

    # Build requests and the custom_id → index map.
    requests: list[dict] = []
    custom_id_to_index: dict[str, int] = {}
    for i, record in enumerate(records):
        custom_id = f"r{i:06d}"
        req = build_batch_request(
            custom_id=custom_id,
            judge_model=judge_model,
            task=record["task"],
            question=record["question"],
            gold=record["gold"],
            response=record["raw_output"],
            max_tokens=max_tokens,
        )
        requests.append(req)
        custom_id_to_index[custom_id] = i

    # Write JSONL sidecar next to the state file.
    state_path.parent.mkdir(parents=True, exist_ok=True)
    jsonl_path = state_path.with_suffix(".requests.jsonl")
    with open(jsonl_path, "w", encoding="utf-8") as handle:
        for req in requests:
            handle.write(json.dumps(req) + "\n")

    client = _openai_client()
    print(
        f"judge_openai: uploading {len(requests)} requests ({jsonl_path})",
        file=sys.stderr,
    )
    with open(jsonl_path, "rb") as fh:
        file_obj = client.files.create(file=fh, purpose="batch")

    print(
        f"judge_openai: submitting batch (input_file_id={file_obj.id})",
        file=sys.stderr,
    )
    batch = client.batches.create(
        input_file_id=file_obj.id,
        endpoint="/v1/chat/completions",
        completion_window=DEFAULT_COMPLETION_WINDOW,
    )

    state = {
        "batch_id": batch.id,
        "input_file_id": file_obj.id,
        "judge_model": judge_model,
        "prompt_version": PROMPT_VERSION,
        "custom_id_to_index": custom_id_to_index,
        "submitted_at": datetime.now(timezone.utc).isoformat(),
        "request_count": len(requests),
    }
    save_state(state_path, state)

    print(f"judge_openai: batch_id={batch.id}")
    print(f"judge_openai: state written to {state_path}")
    print(
        f"judge_openai: next -> python judge_openai.py poll --state {state_path}"
    )
    return 0


def cmd_poll(args: argparse.Namespace) -> int:
    state_path = Path(args.state)
    state = load_state(state_path)
    batch_id = state["batch_id"]
    client = _openai_client()

    interval = getattr(args, "interval", DEFAULT_POLL_INTERVAL)
    once = getattr(args, "once", False)

    while True:
        batch = client.batches.retrieve(batch_id)
        status = batch.status
        counts = getattr(batch, "request_counts", None)
        completed = getattr(counts, "completed", 0) if counts else 0
        failed = getattr(counts, "failed", 0) if counts else 0
        total = getattr(counts, "total", 0) if counts else 0
        now = datetime.now().strftime("%H:%M:%S")
        print(
            f"[{now}] status={status} completed={completed}/{total} failed={failed}",
            file=sys.stderr,
        )

        if status in ("completed", "failed", "cancelled", "expired"):
            state["status"] = status
            state["output_file_id"] = getattr(batch, "output_file_id", None)
            state["error_file_id"] = getattr(batch, "error_file_id", None)
            state["finished_at"] = datetime.now(timezone.utc).isoformat()
            save_state(state_path, state)
            return 0 if status == "completed" else 1

        if once:
            return 2  # still in progress, not a terminal state

        time.sleep(interval)


def cmd_retrieve(args: argparse.Namespace) -> int:
    state_path = Path(args.state)
    state = load_state(state_path)
    output_file_id = state.get("output_file_id")
    if not output_file_id:
        print(
            "judge_openai retrieve: no output_file_id in state — run poll first",
            file=sys.stderr,
        )
        return 1

    client = _openai_client()
    content = client.files.content(output_file_id)
    # openai SDK returns an HttpxBinaryResponseContent; handle both shapes.
    if hasattr(content, "text"):
        output_text = content.text
    else:
        output_text = content.read().decode("utf-8")

    verdicts: dict[str, bool | None] = {}
    for line in output_text.strip().split("\n"):
        if not line:
            continue
        cid, verdict = parse_batch_result_line(line)
        verdicts[cid] = verdict

    with open(args.input, encoding="utf-8") as handle:
        payload = json.load(handle)
    records = payload["records"]

    custom_id_to_index = state["custom_id_to_index"]
    for cid, idx in custom_id_to_index.items():
        records[idx]["judge_correct"] = verdicts.get(cid)

    payload["records"] = records
    payload["summary"] = summarize(records)
    payload["meta"]["judge_model"] = state["judge_model"]
    payload["meta"]["judge_backend"] = "openai-batch"
    payload["meta"]["judged_at"] = datetime.now(timezone.utc).isoformat()
    payload["meta"]["prompt_version"] = state["prompt_version"]

    output_path = Path(args.output)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    with open(output_path, "w", encoding="utf-8") as handle:
        json.dump(payload, handle, indent=2)
        handle.write("\n")

    print(f"judge_openai: wrote {output_path}")
    return 0


def cmd_run(args: argparse.Namespace) -> int:
    submit_args = argparse.Namespace(
        input=args.input,
        state=args.state,
        judge_model=args.judge_model,
        max_tokens=args.max_tokens,
    )
    rc = cmd_submit(submit_args)
    if rc != 0:
        return rc

    poll_args = argparse.Namespace(
        state=args.state,
        interval=args.interval,
        once=False,
    )
    rc = cmd_poll(poll_args)
    if rc != 0:
        return rc

    retrieve_args = argparse.Namespace(
        state=args.state,
        input=args.input,
        output=args.output,
    )
    return cmd_retrieve(retrieve_args)


# ---------------------------------------------------------------------------
# Parser
# ---------------------------------------------------------------------------


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="judge_openai",
        description="OpenAI batch-API judge for the format-tax release.",
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    sub = parser.add_subparsers(dest="subcommand", required=True)

    def add_submit_args(p):
        p.add_argument("--input", required=True, help="input raw.json with records")
        p.add_argument(
            "--state",
            required=True,
            help="path to state file (batch_id + custom_id→index mapping)",
        )
        p.add_argument(
            "--judge-model",
            default=DEFAULT_JUDGE_MODEL,
            help=f"OpenAI model id (default: {DEFAULT_JUDGE_MODEL})",
        )
        p.add_argument(
            "--max-tokens",
            type=int,
            default=DEFAULT_MAX_OUTPUT_TOKENS,
            help=f"max_completion_tokens per judge call (default: {DEFAULT_MAX_OUTPUT_TOKENS})",
        )

    p_submit = sub.add_parser("submit", help="build, upload, and submit a batch job")
    add_submit_args(p_submit)
    p_submit.set_defaults(func=cmd_submit)

    p_poll = sub.add_parser("poll", help="check batch status")
    p_poll.add_argument("--state", required=True)
    p_poll.add_argument(
        "--interval",
        type=int,
        default=DEFAULT_POLL_INTERVAL,
        help=f"poll interval in seconds (default: {DEFAULT_POLL_INTERVAL})",
    )
    p_poll.add_argument(
        "--once",
        action="store_true",
        help="check status once and exit (instead of looping)",
    )
    p_poll.set_defaults(func=cmd_poll)

    p_retrieve = sub.add_parser(
        "retrieve",
        help="download batch output and apply verdicts to records",
    )
    p_retrieve.add_argument("--state", required=True)
    p_retrieve.add_argument("--input", required=True, help="original raw.json")
    p_retrieve.add_argument("--output", required=True, help="judged .json path")
    p_retrieve.set_defaults(func=cmd_retrieve)

    p_run = sub.add_parser("run", help="submit → poll → retrieve in one shot")
    add_submit_args(p_run)
    p_run.add_argument("--output", required=True, help="judged .json path")
    p_run.add_argument(
        "--interval",
        type=int,
        default=DEFAULT_POLL_INTERVAL,
        help=f"poll interval in seconds (default: {DEFAULT_POLL_INTERVAL})",
    )
    p_run.set_defaults(func=cmd_run)

    return parser


def main(argv: list[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    return args.func(args)


if __name__ == "__main__":
    sys.exit(main())
