"""Property-style tests spanning multiple modules.

These check invariants that must hold for *any* input, not just the
specific examples exercised in the per-module test files.
"""

import itertools

from promptgate import Gate
from promptgate.safety import validate
from promptgate.scrub import Scrubber

FAKE_AWS_KEY = "AKIA" + "X" * 16


def tool_call_message(call_id, content_len=50):
    return {
        "role": "assistant",
        "content": None,
        "tool_calls": [{"id": call_id, "function": {"name": "search", "arguments": "{}"}}],
    }


def build_conversation(n_turns, tool_every=3, secret_every=5, pii_every=4):
    messages = [{"role": "system", "content": "You are a helpful assistant."}]
    for i in range(n_turns):
        text = f"turn {i}: tell me something"
        if pii_every and i % pii_every == 0:
            text += " my email is bob@example.com"
        if secret_every and i % secret_every == 0:
            text += f" here is a key {FAKE_AWS_KEY}"
        messages.append({"role": "user", "content": text})
        if tool_every and i % tool_every == 0:
            call_id = f"call_{i}"
            messages.append(tool_call_message(call_id))
            messages.append(
                {
                    "role": "tool",
                    "tool_call_id": call_id,
                    "name": "search",
                    "content": "result " * 200,
                }
            )
        messages.append({"role": "assistant", "content": f"answer {i}"})
    return messages


class TestScrubIdempotency:
    def test_idempotent_across_many_configs(self):
        scrubber = Scrubber(categories=["secrets", "email", "phone", "ssn", "ip"])
        samples = [
            "nothing interesting here",
            f"my key is {FAKE_AWS_KEY} and email bob@example.com",
            "password=hunterXXXX123 call 415-555-0199",
            "ssn 123-45-6789 at 10.0.0.1",
        ]
        for sample in samples:
            once, _, _ = scrubber.scrub_text(sample)
            twice, report, _ = scrubber.scrub_text(once)
            assert once == twice
            assert report.secrets == []
            assert report.pii_counts == {}


class TestRehydrateRoundTrip:
    def test_round_trip_restores_original_for_varied_pii(self):
        gate = Gate(budget=100_000)
        samples = [
            "bob@example.com",
            "bob@example.com and alice@example.com",
            "call 415-555-0199 or email carol@example.com",
        ]
        for original in samples:
            messages = [{"role": "user", "content": original}]
            safe, pii_map = gate.prepare(messages)
            restored = gate.rehydrate(safe[0]["content"], pii_map)
            assert restored == original


class TestPrepareAlwaysValid:
    def test_prepare_output_always_passes_validate(self):
        budgets = [None, 10, 50, 200, 1000, 100_000]
        compress_modes = ["window", "truncate_tools", "hybrid"]
        for budget, compress in itertools.product(budgets, compress_modes):
            gate = Gate(budget=budget, compress=compress, keep_last=2)
            messages = build_conversation(n_turns=12)
            safe, _pii_map = gate.prepare(messages)
            validate(safe)  # must never raise
            assert len(safe) >= 1  # never empty for non-empty input

    def test_prepare_never_empty_for_single_oversized_message(self):
        gate = Gate(budget=5, compress="hybrid")
        messages = [{"role": "user", "content": "x" * 5000}]
        safe, _ = gate.prepare(messages)
        assert len(safe) == 1
        validate(safe)
