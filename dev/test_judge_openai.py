"""Tests for the OpenAI batch-API judge backend.

Run with: `uvx --with jinja2 pytest dev/test_judge_openai.py`

The openai python SDK is mocked in all tests — no real API calls are
made. We only exercise the pure builders (batch request construction,
result parsing, state save/load) and the command handlers with a
fake OpenAI client.
"""

from __future__ import annotations

import importlib.util
import json
import sys
from importlib.machinery import SourceFileLoader
from pathlib import Path
from unittest import mock

import pytest


_HERE = Path(__file__).resolve().parent
_REPO_ROOT = _HERE.parent
_MODULE_PATH = _REPO_ROOT / "judge_openai.py"

if str(_REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(_REPO_ROOT))


def _load_module():
    loader = SourceFileLoader("judge_openai", str(_MODULE_PATH))
    spec = importlib.util.spec_from_loader("judge_openai", loader)
    module = importlib.util.module_from_spec(spec)
    loader.exec_module(module)
    return module


judge_openai = _load_module()


# ---------------------------------------------------------------------------
# build_batch_request
# ---------------------------------------------------------------------------


class TestBuildBatchRequest:
    def test_returns_dict_with_core_fields(self):
        req = judge_openai.build_batch_request(
            custom_id="r00001",
            judge_model="gpt-5.4-nano",
            task="math500",
            question="q",
            gold="g",
            response="r",
        )
        assert req["custom_id"] == "r00001"
        assert req["method"] == "POST"
        assert req["url"] == "/v1/chat/completions"
        assert isinstance(req["body"], dict)

    def test_body_model_matches(self):
        req = judge_openai.build_batch_request(
            custom_id="r00001",
            judge_model="gpt-5.4-nano",
            task="math500",
            question="q",
            gold="g",
            response="r",
        )
        assert req["body"]["model"] == "gpt-5.4-nano"

    def test_body_has_messages(self):
        req = judge_openai.build_batch_request(
            custom_id="r00001",
            judge_model="gpt-5.4-nano",
            task="math500",
            question="q",
            gold="g",
            response="r",
        )
        assert "messages" in req["body"]
        assert req["body"]["messages"][0]["role"] == "user"

    def test_body_temperature_is_zero(self):
        req = judge_openai.build_batch_request(
            custom_id="r00001",
            judge_model="gpt-5.4-nano",
            task="math500",
            question="q",
            gold="g",
            response="r",
        )
        # Allow either temperature or reasoning config, but temperature
        # (when present) must be 0
        temp = req["body"].get("temperature")
        if temp is not None:
            assert temp == 0.0

    def test_uses_task_specific_prompt_math500(self):
        req = judge_openai.build_batch_request(
            custom_id="r00001",
            judge_model="gpt-5.4-nano",
            task="math500",
            question="q",
            gold="g",
            response="r",
        )
        content = req["body"]["messages"][0]["content"]
        assert "mathematical" in content.lower() or "1/2" in content

    def test_uses_task_specific_prompt_gpqa(self):
        req = judge_openai.build_batch_request(
            custom_id="r00001",
            judge_model="gpt-5.4-nano",
            task="gpqa",
            question="q",
            gold="g",
            response="r",
        )
        content = req["body"]["messages"][0]["content"]
        assert "multiple" in content.lower() and "choice" in content.lower()

    def test_uses_task_specific_prompt_zebralogic(self):
        req = judge_openai.build_batch_request(
            custom_id="r00001",
            judge_model="gpt-5.4-nano",
            task="zebralogic",
            question="q",
            gold="g",
            response="r",
        )
        content = req["body"]["messages"][0]["content"]
        assert "logic" in content.lower() and "puzzle" in content.lower()

    def test_rejects_unknown_task(self):
        with pytest.raises(Exception):
            judge_openai.build_batch_request(
                custom_id="r00001",
                judge_model="gpt-5.4-nano",
                task="unknown",
                question="q",
                gold="g",
                response="r",
            )

    def test_content_includes_placeholders_substituted(self):
        req = judge_openai.build_batch_request(
            custom_id="r00001",
            judge_model="gpt-5.4-nano",
            task="math500",
            question="QUESTION_MARKER",
            gold="GOLD_MARKER",
            response="RESPONSE_MARKER",
        )
        content = req["body"]["messages"][0]["content"]
        assert "QUESTION_MARKER" in content
        assert "GOLD_MARKER" in content
        assert "RESPONSE_MARKER" in content


# ---------------------------------------------------------------------------
# parse_batch_result_line
# ---------------------------------------------------------------------------


def _make_result(custom_id: str, content: str, status_code: int = 200) -> str:
    return json.dumps(
        {
            "custom_id": custom_id,
            "response": {
                "status_code": status_code,
                "body": {
                    "choices": [
                        {"message": {"role": "assistant", "content": content}}
                    ]
                },
            },
        }
    )


class TestParseBatchResultLine:
    def test_correct_verdict(self):
        line = _make_result("r00001", "Some reasoning... [[CORRECT]]")
        cid, verdict = judge_openai.parse_batch_result_line(line)
        assert cid == "r00001"
        assert verdict is True

    def test_incorrect_verdict(self):
        line = _make_result("r00001", "[[INCORRECT]]")
        cid, verdict = judge_openai.parse_batch_result_line(line)
        assert cid == "r00001"
        assert verdict is False

    def test_no_verdict_token_returns_none(self):
        line = _make_result("r00001", "The student is confused.")
        cid, verdict = judge_openai.parse_batch_result_line(line)
        assert cid == "r00001"
        assert verdict is None

    def test_non_200_status_returns_none(self):
        line = _make_result("r00001", "[[CORRECT]]", status_code=500)
        cid, verdict = judge_openai.parse_batch_result_line(line)
        assert cid == "r00001"
        assert verdict is None

    def test_empty_choices_returns_none(self):
        line = json.dumps(
            {
                "custom_id": "r00001",
                "response": {"status_code": 200, "body": {"choices": []}},
            }
        )
        cid, verdict = judge_openai.parse_batch_result_line(line)
        assert cid == "r00001"
        assert verdict is None

    def test_missing_response_returns_none(self):
        line = json.dumps(
            {"custom_id": "r00001", "error": {"code": "rate_limited"}}
        )
        cid, verdict = judge_openai.parse_batch_result_line(line)
        assert cid == "r00001"
        assert verdict is None

    def test_case_insensitive_verdict(self):
        line = _make_result("r00001", "[[correct]]")
        cid, verdict = judge_openai.parse_batch_result_line(line)
        assert verdict is True


# ---------------------------------------------------------------------------
# state save/load
# ---------------------------------------------------------------------------


class TestStateSaveLoad:
    def test_roundtrip(self, tmp_path):
        state = {
            "batch_id": "batch_abc",
            "input_file_id": "file_xyz",
            "judge_model": "gpt-5.4-nano",
            "prompt_version": "v2",
            "custom_id_to_index": {"r00000": 0, "r00001": 1},
            "submitted_at": "2026-04-10T22:30:00+00:00",
            "request_count": 2,
        }
        path = tmp_path / "state.json"
        judge_openai.save_state(path, state)
        loaded = judge_openai.load_state(path)
        assert loaded == state

    def test_save_creates_parent_dirs(self, tmp_path):
        path = tmp_path / "nested" / "dir" / "state.json"
        judge_openai.save_state(path, {"batch_id": "x"})
        assert path.exists()


# ---------------------------------------------------------------------------
# cmd_submit with mocked OpenAI client
# ---------------------------------------------------------------------------


def _make_fake_records(n: int = 3) -> dict:
    return {
        "meta": {"model": "Qwen/Qwen3-8B", "tasks": ["math500"]},
        "records": [
            {
                "example_id": str(i),
                "task": "math500",
                "format": "freeform",
                "decoding": "prompt",
                "question": f"Q{i}",
                "prompt": f"P{i}",
                "gold": f"G{i}",
                "raw_output": f"R{i}",
                "extracted_answer": f"G{i}",
                "output_tokens": 10,
            }
            for i in range(n)
        ],
    }


class TestCmdSubmit:
    def test_writes_state_and_jsonl(self, tmp_path):
        input_path = tmp_path / "input.raw.json"
        state_path = tmp_path / "state.json"
        with open(input_path, "w") as f:
            json.dump(_make_fake_records(3), f)

        fake_client = mock.MagicMock()
        fake_client.files.create.return_value = mock.MagicMock(id="file_xyz")
        fake_batch = mock.MagicMock(id="batch_abc")
        fake_client.batches.create.return_value = fake_batch

        args = mock.MagicMock(
            input=str(input_path),
            state=str(state_path),
            judge_model="gpt-5.4-nano",
            max_tokens=512,
        )

        with mock.patch.object(
            judge_openai, "_openai_client", return_value=fake_client
        ):
            rc = judge_openai.cmd_submit(args)

        assert rc == 0
        assert state_path.exists()
        state = json.loads(state_path.read_text())
        assert state["batch_id"] == "batch_abc"
        assert state["input_file_id"] == "file_xyz"
        assert state["judge_model"] == "gpt-5.4-nano"
        assert state["request_count"] == 3
        assert len(state["custom_id_to_index"]) == 3

        # JSONL sidecar should exist and have 3 lines
        jsonl_path = state_path.with_suffix(".requests.jsonl")
        assert jsonl_path.exists()
        lines = jsonl_path.read_text().strip().split("\n")
        assert len(lines) == 3
        first = json.loads(lines[0])
        assert first["method"] == "POST"
        assert first["url"] == "/v1/chat/completions"
        assert first["body"]["model"] == "gpt-5.4-nano"

    def test_submit_calls_files_create_and_batches_create(self, tmp_path):
        input_path = tmp_path / "input.raw.json"
        state_path = tmp_path / "state.json"
        with open(input_path, "w") as f:
            json.dump(_make_fake_records(2), f)

        fake_client = mock.MagicMock()
        fake_client.files.create.return_value = mock.MagicMock(id="file_xyz")
        fake_client.batches.create.return_value = mock.MagicMock(id="batch_abc")

        args = mock.MagicMock(
            input=str(input_path),
            state=str(state_path),
            judge_model="gpt-5.4-nano",
            max_tokens=512,
        )

        with mock.patch.object(
            judge_openai, "_openai_client", return_value=fake_client
        ):
            judge_openai.cmd_submit(args)

        assert fake_client.files.create.called
        assert fake_client.batches.create.called
        create_kwargs = fake_client.batches.create.call_args.kwargs
        assert create_kwargs["input_file_id"] == "file_xyz"
        assert create_kwargs["endpoint"] == "/v1/chat/completions"


# ---------------------------------------------------------------------------
# cmd_retrieve with mocked OpenAI client
# ---------------------------------------------------------------------------


class TestCmdRetrieve:
    def test_applies_verdicts_and_writes_output(self, tmp_path):
        input_path = tmp_path / "input.raw.json"
        state_path = tmp_path / "state.json"
        output_path = tmp_path / "output.json"

        payload = _make_fake_records(3)
        with open(input_path, "w") as f:
            json.dump(payload, f)

        state = {
            "batch_id": "batch_abc",
            "input_file_id": "file_xyz",
            "output_file_id": "file_out",
            "judge_model": "gpt-5.4-nano",
            "prompt_version": "v2",
            "custom_id_to_index": {"r000000": 0, "r000001": 1, "r000002": 2},
            "submitted_at": "2026-04-10T22:30:00+00:00",
            "request_count": 3,
        }
        judge_openai.save_state(state_path, state)

        # Mock OpenAI file download
        verdicts_jsonl = "\n".join(
            [
                _make_result("r000000", "[[CORRECT]]"),
                _make_result("r000001", "[[INCORRECT]]"),
                _make_result("r000002", "unclear"),
            ]
        )
        fake_file_content = mock.MagicMock()
        fake_file_content.text = verdicts_jsonl
        # Also support .read().decode() path
        fake_file_content.read = lambda: verdicts_jsonl.encode("utf-8")

        fake_client = mock.MagicMock()
        fake_client.files.content.return_value = fake_file_content

        args = mock.MagicMock(
            input=str(input_path),
            output=str(output_path),
            state=str(state_path),
        )

        with mock.patch.object(
            judge_openai, "_openai_client", return_value=fake_client
        ):
            rc = judge_openai.cmd_retrieve(args)

        assert rc == 0
        out = json.loads(output_path.read_text())
        records = out["records"]
        assert records[0]["judge_correct"] is True
        assert records[1]["judge_correct"] is False
        assert records[2]["judge_correct"] is None
        assert "summary" in out
        assert out["meta"]["judge_model"] == "gpt-5.4-nano"
        assert out["meta"]["judge_backend"] == "openai-batch"


# ---------------------------------------------------------------------------
# Parser
# ---------------------------------------------------------------------------


class TestParser:
    def test_submit_subcommand(self):
        parser = judge_openai.build_parser()
        args = parser.parse_args(
            ["submit", "--input", "raw.json", "--state", "state.json"]
        )
        assert args.subcommand == "submit"
        assert args.input == "raw.json"
        assert args.state == "state.json"

    def test_submit_default_model_is_nano(self):
        parser = judge_openai.build_parser()
        args = parser.parse_args(
            ["submit", "--input", "raw.json", "--state", "state.json"]
        )
        assert args.judge_model == "gpt-5.4-nano"

    def test_poll_subcommand(self):
        parser = judge_openai.build_parser()
        args = parser.parse_args(["poll", "--state", "state.json"])
        assert args.subcommand == "poll"

    def test_retrieve_subcommand(self):
        parser = judge_openai.build_parser()
        args = parser.parse_args(
            [
                "retrieve",
                "--state",
                "state.json",
                "--input",
                "raw.json",
                "--output",
                "out.json",
            ]
        )
        assert args.subcommand == "retrieve"

    def test_run_subcommand_chains_everything(self):
        parser = judge_openai.build_parser()
        args = parser.parse_args(
            [
                "run",
                "--input",
                "raw.json",
                "--output",
                "out.json",
                "--state",
                "state.json",
            ]
        )
        assert args.subcommand == "run"
