from promptgate import counters, safety
from promptgate.strategies import window


def msg(role, content, **extra):
    m = {"role": role, "content": content}
    m.update(extra)
    return m


def long_text(n_tokens):
    # heuristic counter is ceil(len/3); pad generously
    return "x" * (n_tokens * 3 + 3)


class TestEdgeCases:
    def test_empty_list(self):
        result, warnings = window.apply([], budget=1000)
        assert result == []
        assert warnings == []

    def test_already_under_budget_is_identity(self):
        messages = [msg("system", "sys"), msg("user", "hi")]
        result, warnings = window.apply(messages, budget=10_000)
        assert result is messages
        assert warnings == []

    def test_none_budget_is_identity(self):
        messages = [msg("user", "hi")]
        result, warnings = window.apply(messages, budget=None)
        assert result == messages
        assert warnings == []

    def test_single_message_exceeding_budget_is_kept_with_warning(self):
        messages = [msg("user", long_text(500))]
        result, warnings = window.apply(messages, budget=10, keep_last=6)
        assert len(result) == 1
        assert result[0] == messages[0]
        assert warnings

    def test_never_returns_empty_for_nonempty_input(self):
        messages = [msg("assistant", long_text(500))]
        result, warnings = window.apply(messages, budget=1, keep_last=0, pin=())
        assert len(result) == 1

    def test_never_evicts_most_recent_user_message(self):
        messages = [msg("user", long_text(200)) for _ in range(10)]
        result, _ = window.apply(messages, budget=5, keep_last=0, pin=())
        assert result[-1] == messages[-1]

    def test_tool_call_evicted_but_result_survives_gets_repaired(self):
        messages = [
            msg("system", "sys"),
            msg("user", "old question " + long_text(300)),
            msg(
                "assistant",
                None,
                tool_calls=[{"id": "call_1", "function": {"name": "f", "arguments": "{}"}}],
            ),
            msg("tool", "result", tool_call_id="call_1", name="f"),
            msg("user", "final question"),
        ]
        # tight budget: only system + tail (keep_last=1 -> last message) fit
        result, _ = window.apply(messages, budget=15, keep_last=1)
        safety.validate(result)  # must not raise
        # the assistant tool_calls message got evicted, so its result must be gone too
        tool_messages = [m for m in result if m.get("role") == "tool"]
        assert tool_messages == []

    def test_pinned_system_always_kept(self):
        messages = [msg("system", "sys"), *[msg("user", long_text(300)) for _ in range(20)]]
        result, _ = window.apply(messages, budget=20, keep_last=1)
        assert result[0]["role"] == "system"

    def test_zero_assistant_messages_window_only(self):
        messages = [msg("user", long_text(50)) for _ in range(5)]
        result, _ = window.apply(messages, budget=30, keep_last=1)
        assert len(result) >= 1
        assert result[-1] == messages[-1]


class TestBudgetRespected:
    def test_evicts_oldest_first(self):
        messages = [
            msg("user", f"msg-{i} " + long_text(50)) for i in range(10)
        ]
        result, _ = window.apply(messages, budget=200, keep_last=2)
        # the most recent messages should be present, the earliest evicted
        assert messages[-1] in result
        assert messages[0] not in result

    def test_result_fits_budget_when_possible(self):
        messages = [msg("user", f"m{i}") for i in range(5)]
        result, _ = window.apply(messages, budget=1000, keep_last=1)
        assert counters.count_messages(result) <= 1000

    def test_keep_last_respected(self):
        messages = [msg("user", long_text(10)) for _ in range(10)]
        result, _ = window.apply(messages, budget=10_000, keep_last=3)
        assert result[-3:] == messages[-3:]

    def test_output_always_passes_validate(self):
        messages = [
            msg("system", "sys"),
            msg("user", long_text(100)),
            msg(
                "assistant",
                None,
                tool_calls=[{"id": "c1", "function": {"name": "f", "arguments": "{}"}}],
            ),
            msg("tool", "r", tool_call_id="c1", name="f"),
            msg("assistant", "answer " + long_text(100)),
            msg("user", "final"),
        ]
        result, _ = window.apply(messages, budget=25, keep_last=1)
        safety.validate(result)
