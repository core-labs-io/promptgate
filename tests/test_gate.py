import pytest

from promptgate import Gate
from promptgate.gate import Gate as GateFromModule
from promptgate.safety import validate
from promptgate.scrub import SecretFound

FAKE_AWS_KEY = "AKIA" + "X" * 16


def long_text(n_tokens):
    return "x" * (n_tokens * 3 + 3)


class TestConstruction:
    def test_invalid_compress_mode_raises(self):
        with pytest.raises(ValueError):
            Gate(compress="bogus")

    def test_gate_is_exported_from_package_root(self):
        assert Gate is GateFromModule


class TestPrepareIdentity:
    def test_identity_when_nothing_to_scrub_and_under_budget(self):
        gate = Gate(budget=10_000)
        messages = [{"role": "system", "content": "sys"}, {"role": "user", "content": "hi"}]
        safe, pii_map = gate.prepare(messages)
        assert safe == messages
        assert pii_map == {}

    def test_empty_messages(self):
        gate = Gate(budget=1000)
        safe, pii_map = gate.prepare([])
        assert safe == []
        assert pii_map == {}

    def test_no_budget_means_no_compression(self):
        gate = Gate(budget=None)
        messages = [{"role": "user", "content": long_text(10_000)}]
        safe, _ = gate.prepare(messages)
        assert safe == messages


class TestPrepareScrubbing:
    def test_email_is_masked(self):
        gate = Gate(budget=10_000)
        messages = [{"role": "user", "content": "reach me at bob@example.com"}]
        safe, pii_map = gate.prepare(messages)
        assert "bob@example.com" not in safe[0]["content"]
        assert "[[EMAIL_1]]" in safe[0]["content"]
        assert pii_map["[[EMAIL_1]]"] == "bob@example.com"

    def test_secret_is_masked_and_never_in_pii_map(self):
        gate = Gate(budget=10_000, on_secret="mask")
        messages = [{"role": "user", "content": FAKE_AWS_KEY}]
        safe, pii_map = gate.prepare(messages)
        assert FAKE_AWS_KEY not in safe[0]["content"]
        assert FAKE_AWS_KEY not in pii_map.values()
        assert pii_map == {}

    def test_on_secret_raise_propagates(self):
        gate = Gate(budget=10_000, on_secret="raise")
        messages = [{"role": "user", "content": FAKE_AWS_KEY}]
        with pytest.raises(SecretFound) as exc_info:
            gate.prepare(messages)
        assert FAKE_AWS_KEY not in str(exc_info.value)

    def test_pii_map_continuity_across_turns(self):
        gate = Gate(budget=10_000)
        turn1 = [{"role": "user", "content": "I'm bob@example.com"}]
        _safe1, pii_map1 = gate.prepare(turn1)

        turn2 = [
            {"role": "user", "content": "I'm bob@example.com"},
            {"role": "assistant", "content": "noted"},
            {"role": "user", "content": "also alice@example.com"},
        ]
        safe2, pii_map2 = gate.prepare(turn2, pii_map=pii_map1)
        assert "[[EMAIL_1]]" in safe2[0]["content"]
        assert "[[EMAIL_2]]" in safe2[2]["content"]
        assert len(pii_map2) == 2

    def test_scrub_categories_configurable(self):
        gate = Gate(budget=10_000, scrub=["email"])
        messages = [{"role": "user", "content": f"{FAKE_AWS_KEY} bob@example.com"}]
        safe, pii_map = gate.prepare(messages)
        assert FAKE_AWS_KEY in safe[0]["content"]
        assert "bob@example.com" not in safe[0]["content"]


class TestPrepareCompression:
    def test_hybrid_truncates_then_windows(self):
        gate = Gate(budget=30, compress="hybrid", keep_last=1)
        messages = [
            {"role": "system", "content": "sys"},
            {"role": "user", "content": "q1 " + long_text(200)},
            {
                "role": "assistant",
                "content": None,
                "tool_calls": [{"id": "c1", "function": {"name": "f", "arguments": "{}"}}],
            },
            {"role": "tool", "tool_call_id": "c1", "name": "f", "content": long_text(200)},
            {"role": "user", "content": "final question"},
        ]
        safe, _ = gate.prepare(messages)
        validate(safe)
        assert safe[-1]["content"] == "final question"

    def test_window_mode_only(self):
        gate = Gate(budget=20, compress="window", keep_last=1)
        messages = [{"role": "user", "content": long_text(50)} for _ in range(10)]
        safe, _ = gate.prepare(messages)
        validate(safe)
        assert safe[-1] == messages[-1]

    def test_truncate_tools_mode_never_evicts_messages(self):
        gate = Gate(budget=10, compress="truncate_tools")
        messages = [
            {"role": "user", "content": "q"},
            {
                "role": "assistant",
                "content": None,
                "tool_calls": [{"id": "c1", "function": {"name": "f", "arguments": "{}"}}],
            },
            {"role": "tool", "tool_call_id": "c1", "name": "f", "content": long_text(200)},
            {"role": "user", "content": "next"},
            {"role": "assistant", "content": "answer"},
            {"role": "user", "content": "another"},
        ]
        safe, _ = gate.prepare(messages)
        assert len(safe) == len(messages)
        assert safe[2]["content"].startswith("[tool result truncated")

    def test_output_always_valid_structure(self):
        gate = Gate(budget=15, keep_last=1)
        messages = [
            {"role": "system", "content": "sys"},
            {"role": "user", "content": long_text(100)},
            {
                "role": "assistant",
                "content": None,
                "tool_calls": [{"id": "c1", "function": {"name": "f", "arguments": "{}"}}],
            },
            {"role": "tool", "tool_call_id": "c1", "name": "f", "content": "r"},
            {"role": "assistant", "content": "answer " + long_text(100)},
            {"role": "user", "content": "final"},
        ]
        safe, _ = gate.prepare(messages)
        validate(safe)  # must not raise


class TestExplain:
    def test_does_not_mutate_input(self):
        gate = Gate(budget=10_000)
        messages = [{"role": "user", "content": "bob@example.com"}]
        gate.explain(messages)
        assert messages[0]["content"] == "bob@example.com"

    def test_reports_tokens_and_pii(self):
        gate = Gate(budget=10_000)
        messages = [{"role": "user", "content": "reach me at bob@example.com"}]
        report = gate.explain(messages)
        assert report.tokens_before > 0
        assert report.pii_counts.get("EMAIL") == 1
        assert report.structure_valid is True

    def test_never_raises_even_with_on_secret_raise(self):
        gate = Gate(budget=10_000, on_secret="raise")
        messages = [{"role": "user", "content": FAKE_AWS_KEY}]
        report = gate.explain(messages)
        assert len(report.secrets) == 1
        assert report.secrets[0].category == "AWS"

    def test_str_produces_hero_block(self):
        gate = Gate(budget=10_000)
        messages = [{"role": "user", "content": "bob@example.com"}]
        text = str(gate.explain(messages))
        assert text.startswith("promptgate report")


class TestRehydrate:
    def test_restores_clean_placeholder(self):
        gate = Gate()
        pii_map = {"[[EMAIL_1]]": "bob@example.com"}
        assert gate.rehydrate("contact [[EMAIL_1]]", pii_map) == "contact bob@example.com"

    def test_tolerates_extra_spaces(self):
        gate = Gate()
        pii_map = {"[[EMAIL_1]]": "bob@example.com"}
        assert gate.rehydrate("contact [[ EMAIL_1 ]]", pii_map) == "contact bob@example.com"

    def test_tolerates_single_brackets(self):
        gate = Gate()
        pii_map = {"[[EMAIL_1]]": "bob@example.com"}
        assert gate.rehydrate("contact [EMAIL_1]", pii_map) == "contact bob@example.com"

    def test_tolerates_no_brackets(self):
        gate = Gate()
        pii_map = {"[[EMAIL_1]]": "bob@example.com"}
        assert gate.rehydrate("contact EMAIL_1", pii_map) == "contact bob@example.com"

    def test_unknown_placeholder_left_alone(self):
        gate = Gate()
        assert gate.rehydrate("contact [[EMAIL_1]]", {}) == "contact [[EMAIL_1]]"

    def test_empty_pii_map_is_noop(self):
        gate = Gate()
        assert gate.rehydrate("hello world", {}) == "hello world"

    def test_secrets_never_rehydrated(self):
        gate = Gate(budget=10_000, on_secret="mask")
        messages = [{"role": "user", "content": FAKE_AWS_KEY}]
        safe, pii_map = gate.prepare(messages)
        placeholder = safe[0]["content"]
        restored = gate.rehydrate(placeholder, pii_map)
        assert restored == placeholder  # unchanged: no mapping exists for secrets
        assert FAKE_AWS_KEY not in restored


class TestRoundTrip:
    def test_scrub_then_rehydrate_restores_original_text(self):
        gate = Gate(budget=10_000)
        original = "email bob@example.com or alice@example.com"
        messages = [{"role": "user", "content": original}]
        safe, pii_map = gate.prepare(messages)
        restored = gate.rehydrate(safe[0]["content"], pii_map)
        assert restored == original
