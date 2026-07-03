from promptgate.strategies import tool_truncate


def assistant(tool_calls=None):
    return {"role": "assistant", "content": None, "tool_calls": tool_calls or []}


def tool_result(name="search", content="x", call_id="1"):
    return {"role": "tool", "tool_call_id": call_id, "name": name, "content": content}


class TestBasics:
    def test_empty_list(self):
        assert tool_truncate.apply([]) == []

    def test_small_result_not_stubbed(self):
        messages = [
            {"role": "user", "content": "run it"},
            assistant(),
            tool_result(content="small"),
            {"role": "user", "content": "next"},
            assistant(),
            {"role": "user", "content": "another"},
        ]
        result = tool_truncate.apply(messages, keep_recent_turns=0, stub_threshold_tokens=120)
        assert result[2]["content"] == "small"

    def test_large_old_result_stubbed(self):
        messages = [
            {"role": "user", "content": "run it"},
            assistant(),
            tool_result(name="search", content="x" * 1000),
            {"role": "user", "content": "next"},
            assistant(),
            {"role": "user", "content": "another"},
        ]
        result = tool_truncate.apply(messages, keep_recent_turns=0, stub_threshold_tokens=120)
        assert result[2]["content"].startswith("[tool result truncated: search returned")
        assert result[2]["tool_call_id"] == "1"
        assert result[2]["role"] == "tool"

    def test_recent_turn_not_stubbed_even_if_large(self):
        messages = [
            {"role": "user", "content": "run it"},
            assistant(),
            tool_result(content="x" * 1000),
        ]
        # only one assistant turn total, keep_recent_turns=1 keeps it
        result = tool_truncate.apply(messages, keep_recent_turns=1, stub_threshold_tokens=120)
        assert result[2]["content"] == "x" * 1000

    def test_zero_assistant_messages_no_op(self):
        messages = [
            {"role": "user", "content": "hi"},
            tool_result(content="x" * 1000),
        ]
        result = tool_truncate.apply(messages, keep_recent_turns=1, stub_threshold_tokens=10)
        assert result == messages

    def test_preserves_non_tool_messages(self):
        messages = [{"role": "user", "content": "hi"}]
        assert tool_truncate.apply(messages) == messages

    def test_keep_recent_turns_zero_truncates_everything_old_enough(self):
        messages = [
            assistant(),
            tool_result(content="x" * 1000),
            {"role": "user", "content": "hi"},
            assistant(),
            tool_result(content="y" * 1000, call_id="2"),
        ]
        result = tool_truncate.apply(messages, keep_recent_turns=0, stub_threshold_tokens=10)
        assert result[1]["content"].startswith("[tool result truncated")
        assert result[4]["content"].startswith("[tool result truncated")
