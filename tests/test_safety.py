import pytest

from promptgate.safety import StructureError, repair, validate


def assistant_with_call(call_id, name="get_weather"):
    return {
        "role": "assistant",
        "content": None,
        "tool_calls": [{"id": call_id, "function": {"name": name, "arguments": "{}"}}],
    }


def tool_result(call_id, content="result"):
    return {"role": "tool", "tool_call_id": call_id, "content": content}


class TestValidate:
    def test_empty_list_is_valid(self):
        validate([])

    def test_simple_conversation_is_valid(self):
        validate(
            [
                {"role": "system", "content": "sys"},
                {"role": "user", "content": "hi"},
                {"role": "assistant", "content": "hello"},
            ]
        )

    def test_matched_tool_call_is_valid(self):
        validate(
            [
                {"role": "user", "content": "weather?"},
                assistant_with_call("call_1"),
                tool_result("call_1"),
            ]
        )

    def test_invalid_role_raises(self):
        with pytest.raises(StructureError):
            validate([{"role": "bogus", "content": "x"}])

    def test_system_not_first_raises(self):
        with pytest.raises(StructureError):
            validate([{"role": "user", "content": "hi"}, {"role": "system", "content": "sys"}])

    def test_multiple_system_messages_raises(self):
        with pytest.raises(StructureError):
            validate(
                [
                    {"role": "system", "content": "a"},
                    {"role": "system", "content": "b"},
                ]
            )

    def test_orphaned_tool_result_raises(self):
        with pytest.raises(StructureError):
            validate([tool_result("call_missing")])

    def test_tool_result_before_its_call_raises(self):
        with pytest.raises(StructureError):
            validate([tool_result("call_1"), assistant_with_call("call_1")])


class TestRepair:
    def test_empty_list(self):
        assert repair([]) == []

    def test_no_change_when_valid(self):
        messages = [
            {"role": "user", "content": "weather?"},
            assistant_with_call("call_1"),
            tool_result("call_1"),
        ]
        assert repair(messages) == messages

    def test_drops_orphaned_tool_result(self):
        messages = [tool_result("call_missing")]
        assert repair(messages) == []

    def test_evicted_tool_call_drops_surviving_result(self):
        # Simulates window eviction: the assistant tool_calls message was
        # evicted but its tool result stayed in the tail.
        messages = [
            {"role": "user", "content": "next question"},
            tool_result("call_1"),
        ]
        result = repair(messages)
        assert result == [{"role": "user", "content": "next question"}]

    def test_repaired_output_passes_validate(self):
        messages = [
            {"role": "user", "content": "next question"},
            tool_result("call_1"),
            {"role": "assistant", "content": "answer"},
        ]
        validate(repair(messages))

    def test_preserves_non_tool_messages_and_order(self):
        messages = [
            {"role": "system", "content": "sys"},
            {"role": "user", "content": "hi"},
            {"role": "assistant", "content": "hello"},
        ]
        assert repair(messages) == messages
