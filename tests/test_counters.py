import math

from promptgate.counters import (
    MESSAGE_OVERHEAD_TOKENS,
    count_message,
    count_messages,
    count_text,
)


class TestCountText:
    def test_empty_text_is_zero(self):
        assert count_text("") == 0

    def test_none_like_falsy_is_zero(self):
        assert count_text("", counter=lambda t: 999) == 0

    def test_heuristic_rounds_up(self):
        # 7 chars / 3 per token = 2.33 -> rounds up to 3
        assert count_text("abcdefg") == math.ceil(7 / 3)

    def test_custom_counter_takes_priority(self):
        assert count_text("hello", counter=lambda t: 42) == 42

    def test_custom_counter_receives_text(self):
        seen = {}

        def counter(text):
            seen["text"] = text
            return 1

        count_text("hello world", counter=counter)
        assert seen["text"] == "hello world"


class TestCountMessage:
    def test_includes_overhead(self):
        tokens = count_message({"role": "user", "content": ""})
        assert tokens == MESSAGE_OVERHEAD_TOKENS

    def test_counts_text_content(self):
        tokens = count_message({"role": "user", "content": "hello"})
        assert tokens == MESSAGE_OVERHEAD_TOKENS + count_text("hello")

    def test_counts_name_field(self):
        with_name = count_message({"role": "tool", "content": "x", "name": "get_weather"})
        without_name = count_message({"role": "tool", "content": "x"})
        assert with_name > without_name

    def test_counts_tool_calls(self):
        message = {
            "role": "assistant",
            "content": None,
            "tool_calls": [
                {
                    "id": "call_1",
                    "function": {"name": "get_weather", "arguments": '{"city": "SF"}'},
                }
            ],
        }
        tokens = count_message(message)
        assert tokens > MESSAGE_OVERHEAD_TOKENS

    def test_custom_counter_used_for_all_text(self):
        message = {"role": "user", "content": "hello"}
        tokens = count_message(message, counter=lambda t: 1)
        assert tokens == MESSAGE_OVERHEAD_TOKENS + 1


class TestCountMessages:
    def test_empty_list_is_zero(self):
        assert count_messages([]) == 0

    def test_sums_across_messages(self):
        messages = [
            {"role": "system", "content": "sys"},
            {"role": "user", "content": "hello there"},
        ]
        total = count_messages(messages)
        expected = count_message(messages[0]) + count_message(messages[1])
        assert total == expected
