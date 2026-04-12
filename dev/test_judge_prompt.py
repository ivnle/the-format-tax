"""Tests for task-specific judge prompts.

Run with: `uvx pytest dev/test_judge_prompt.py`

These tests drive the refactor from a single math-centric judge prompt
to task-specific prompts (math500, gpqa, zebralogic).
"""

from __future__ import annotations

import importlib.util
import sys
from importlib.machinery import SourceFileLoader
from pathlib import Path

import pytest


_HERE = Path(__file__).resolve().parent
_REPO_ROOT = _HERE.parent
_JUDGE_PATH = _REPO_ROOT / "judge.py"

# judge.py imports `prompting` from the repo root; put that on sys.path
# so the import works when pytest is run from anywhere.
if str(_REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(_REPO_ROOT))


def _load_judge():
    loader = SourceFileLoader("judge", str(_JUDGE_PATH))
    spec = importlib.util.spec_from_loader("judge", loader)
    module = importlib.util.module_from_spec(spec)
    loader.exec_module(module)
    return module


judge_mod = _load_judge()


class TestPromptsByTask:
    """The module should expose a registry of task-specific prompts."""

    def test_registry_exists(self):
        assert hasattr(judge_mod, "PROMPTS_BY_TASK")

    def test_registry_has_math500(self):
        assert "math500" in judge_mod.PROMPTS_BY_TASK

    def test_registry_has_gpqa(self):
        assert "gpqa" in judge_mod.PROMPTS_BY_TASK

    def test_registry_has_zebralogic(self):
        assert "zebralogic" in judge_mod.PROMPTS_BY_TASK

    def test_prompts_contain_placeholders(self):
        for task, template in judge_mod.PROMPTS_BY_TASK.items():
            assert "{question}" in template, f"{task} missing {{question}}"
            assert "{gold}" in template, f"{task} missing {{gold}}"
            assert "{response}" in template, f"{task} missing {{response}}"

    def test_all_prompts_end_with_verdict_instruction(self):
        for task, template in judge_mod.PROMPTS_BY_TASK.items():
            assert "[[CORRECT]]" in template, f"{task} missing [[CORRECT]]"
            assert "[[INCORRECT]]" in template, f"{task} missing [[INCORRECT]]"


class TestMath500Prompt:
    def test_mentions_mathematical_equivalence(self):
        p = judge_mod.PROMPTS_BY_TASK["math500"]
        assert (
            "mathematical" in p.lower() or "equivalent" in p.lower()
        )

    def test_gives_equivalence_examples(self):
        p = judge_mod.PROMPTS_BY_TASK["math500"]
        assert "1/2" in p or "0.5" in p


class TestGpqaPrompt:
    def test_mentions_multiple_choice(self):
        p = judge_mod.PROMPTS_BY_TASK["gpqa"]
        assert "multiple" in p.lower() and "choice" in p.lower()

    def test_mentions_letter_range_abcd(self):
        p = judge_mod.PROMPTS_BY_TASK["gpqa"]
        # gpqa is A-D only
        assert "A, B, C, or D" in p or "A-D" in p or ("A" in p and "D" in p)

    def test_does_not_mention_math_equivalence(self):
        p = judge_mod.PROMPTS_BY_TASK["gpqa"]
        assert "mathematical" not in p.lower()

    def test_handles_no_answer_case(self):
        """The prompt should tell the judge what to do when the student
        never commits to a final letter — this was a gap in the old
        prompt that caused ambiguity on truncated responses."""
        p = judge_mod.PROMPTS_BY_TASK["gpqa"]
        assert (
            "did not" in p.lower()
            or "no clear" in p.lower()
            or "trailed off" in p.lower()
            or "ran out" in p.lower()
            or "not clearly" in p.lower()
        )

    def test_accepts_content_not_just_letter(self):
        """The judge should accept the underlying option text (or a clear
        paraphrase) as equivalent to the gold letter — models may say
        '10^-4 eV' instead of 'B'."""
        p = judge_mod.PROMPTS_BY_TASK["gpqa"]
        assert "content" in p.lower() or "text" in p.lower()
        # The prompt should say to accept either form
        assert "letter" in p.lower()


class TestZebralogicPrompt:
    def test_mentions_logic_puzzle(self):
        p = judge_mod.PROMPTS_BY_TASK["zebralogic"]
        assert "logic" in p.lower() and "puzzle" in p.lower()

    def test_mentions_letter_range_a_through_f(self):
        p = judge_mod.PROMPTS_BY_TASK["zebralogic"]
        # zebralogic has A-F choices
        assert (
            "A through F" in p
            or "A-F" in p
            or ("A" in p and "F" in p)
        )

    def test_does_not_mention_math_equivalence(self):
        p = judge_mod.PROMPTS_BY_TASK["zebralogic"]
        assert "mathematical" not in p.lower()

    def test_handles_no_answer_case(self):
        """Zebralogic answers frequently run out of tokens mid-reasoning —
        the prompt must say what to do in that case."""
        p = judge_mod.PROMPTS_BY_TASK["zebralogic"]
        assert (
            "ran out" in p.lower()
            or "no clear" in p.lower()
            or "did not" in p.lower()
            or "trailed off" in p.lower()
            or "not clearly" in p.lower()
        )

    def test_accepts_content_not_just_letter(self):
        """The judge should accept the underlying option text (e.g.
        'Peter') as equivalent to the gold letter (e.g. 'D')."""
        p = judge_mod.PROMPTS_BY_TASK["zebralogic"]
        assert "content" in p.lower() or "text" in p.lower()
        assert "letter" in p.lower()


class TestBuildJudgePromptSignature:
    """build_judge_prompt must take a task argument and use the right template."""

    def test_requires_task_argument(self):
        # Calling without task should fail (either TypeError or similar)
        with pytest.raises(TypeError):
            judge_mod.build_judge_prompt(question="q", gold="g", response="r")

    def test_math500_produces_math_prompt(self):
        rendered = judge_mod.build_judge_prompt(
            task="math500", question="q", gold="g", response="r"
        )
        assert (
            "mathematical" in rendered.lower() or "1/2" in rendered
        )

    def test_gpqa_produces_gpqa_prompt(self):
        rendered = judge_mod.build_judge_prompt(
            task="gpqa", question="q", gold="g", response="r"
        )
        assert "multiple" in rendered.lower()

    def test_zebralogic_produces_zebralogic_prompt(self):
        rendered = judge_mod.build_judge_prompt(
            task="zebralogic", question="q", gold="g", response="r"
        )
        assert "logic" in rendered.lower()

    def test_unknown_task_raises(self):
        with pytest.raises(Exception):
            judge_mod.build_judge_prompt(
                task="unknown", question="q", gold="g", response="r"
            )

    def test_placeholders_are_substituted(self):
        rendered = judge_mod.build_judge_prompt(
            task="math500",
            question="QUESTION_PLACEHOLDER",
            gold="GOLD_PLACEHOLDER",
            response="RESPONSE_PLACEHOLDER",
        )
        assert "QUESTION_PLACEHOLDER" in rendered
        assert "GOLD_PLACEHOLDER" in rendered
        assert "RESPONSE_PLACEHOLDER" in rendered
        # Placeholder tokens themselves should be gone after substitution
        assert "{question}" not in rendered
        assert "{gold}" not in rendered
        assert "{response}" not in rendered

    def test_response_is_truncated_to_last_max_chars(self):
        MAX = judge_mod.MAX_RESPONSE_CHARS
        long = "A" * 100 + "B" * MAX
        rendered = judge_mod.build_judge_prompt(
            task="math500", question="q", gold="g", response=long
        )
        # The leading "A"s should be truncated; only the last MAX "B"s kept
        assert "A" * 100 not in rendered
        # The trailing chunk should be present
        assert "B" * 1000 in rendered


class TestCacheKeyIncludesTask:
    """Cache key must include task so verdicts don't mix across prompts."""

    def test_cache_key_takes_task(self):
        # Just verify it accepts task without raising
        judge_mod.cache_key(
            task="math500",
            question="q",
            gold="g",
            response="r",
            judge_model="m",
        )

    def test_cache_key_differs_by_task(self):
        k1 = judge_mod.cache_key(
            task="math500",
            question="same",
            gold="same",
            response="same",
            judge_model="m",
        )
        k2 = judge_mod.cache_key(
            task="gpqa",
            question="same",
            gold="same",
            response="same",
            judge_model="m",
        )
        assert k1 != k2

    def test_cache_key_stable_for_same_inputs(self):
        k1 = judge_mod.cache_key(
            task="math500", question="q", gold="g", response="r", judge_model="m"
        )
        k2 = judge_mod.cache_key(
            task="math500", question="q", gold="g", response="r", judge_model="m"
        )
        assert k1 == k2


class TestPromptVersionBumped:
    def test_prompt_version_is_v4_or_later(self):
        # v4 flips the content-vs-letter tiebreak: content beats letter
        # (transcription errors shouldn't be penalized as reasoning failures)
        assert judge_mod.PROMPT_VERSION not in ("v1", "v2", "v3")


class TestContentBeatsLetterRule:
    """The MC judge prompts (gpqa, zebralogic) must credit responses
    where the student's substantive reasoning got to the correct option
    but they wrote a contradictory letter at the very end. The letter
    is treated as a transcription slip, not a reasoning failure.
    Self-reversals within the prose are still penalized — "I thought X
    but actually Y" commits to Y, not X."""

    def test_gpqa_prompt_mentions_content_beats_letter(self):
        p = judge_mod.PROMPTS_BY_TASK["gpqa"]
        low = p.lower()
        # The prompt must say some form of "content wins over letter when
        # they disagree" / "letter is a transcription slip, don't penalize"
        has_rule = (
            "content beats letter" in low
            or "content wins" in low
            or "transcription slip" in low
            or "transcription error" in low
            or ("wrong letter" in low and ("correct content" in low or "don't penalize" in low))
            or ("trust the content" in low)
        )
        assert has_rule, (
            "gpqa prompt must explicitly state that content wins over letter "
            "when they disagree (transcription errors shouldn't be penalized)"
        )

    def test_zebralogic_prompt_mentions_content_beats_letter(self):
        p = judge_mod.PROMPTS_BY_TASK["zebralogic"]
        low = p.lower()
        has_rule = (
            "content beats letter" in low
            or "content wins" in low
            or "transcription slip" in low
            or "transcription error" in low
            or ("wrong letter" in low and ("correct content" in low or "don't penalize" in low))
            or ("trust the content" in low)
        )
        assert has_rule, (
            "zebralogic prompt must explicitly state that content wins over "
            "letter when they disagree (transcription errors shouldn't be "
            "penalized)"
        )

    def test_mc_prompts_penalize_self_reversal(self):
        """The prompt should say that self-reversals ("I thought X,
        actually Y") commit to the last answer, not the first. A model
        that correctly reasoned to the right answer and then talked
        itself into a wrong one should NOT get credit."""
        for task in ("gpqa", "zebralogic"):
            p = judge_mod.PROMPTS_BY_TASK[task]
            low = p.lower()
            has_rule = (
                "reversal" in low
                or "self-correction" in low
                or "self-corrections" in low
                or "settled on" in low
                or "last one" in low
                or "abandoned" in low
                or "changed their mind" in low
            )
            assert has_rule, (
                f"{task} prompt must explicitly handle self-reversals "
                f"(student changing their mind from right to wrong is still "
                f"incorrect)"
            )

    def test_mc_prompts_still_accept_content_only_answers(self):
        """Regression: a response with only content (no letter) still counts."""
        for task in ("gpqa", "zebralogic"):
            p = judge_mod.PROMPTS_BY_TASK[task]
            low = p.lower()
            accepts_content_only = (
                "content alone" in low
                or "just content" in low
                or "no letter" in low
                or "without a letter" in low
            )
            assert accepts_content_only, (
                f"{task} prompt must still accept content-only answers "
                f"when no letter is given"
            )
