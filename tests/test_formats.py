from promptgate.formats import get_text, has_multimodal, map_text


class TestGetText:
    def test_string_content(self):
        assert get_text({"role": "user", "content": "hello"}) == "hello"

    def test_none_content(self):
        assert get_text({"role": "assistant", "content": None}) == ""

    def test_missing_content(self):
        assert get_text({"role": "assistant"}) == ""

    def test_list_of_text_parts(self):
        message = {
            "role": "user",
            "content": [{"type": "text", "text": "hello "}, {"type": "text", "text": "world"}],
        }
        assert get_text(message) == "hello world"

    def test_list_skips_non_text_parts(self):
        message = {
            "role": "user",
            "content": [
                {"type": "text", "text": "look at this"},
                {"type": "image_url", "image_url": {"url": "https://example.com/x.png"}},
            ],
        }
        assert get_text(message) == "look at this"

    def test_list_with_raw_strings(self):
        message = {"role": "user", "content": ["a", "b"]}
        assert get_text(message) == "ab"


class TestHasMultimodal:
    def test_string_content_is_not_multimodal(self):
        assert has_multimodal({"role": "user", "content": "hi"}) is False

    def test_text_only_parts_not_multimodal(self):
        message = {"role": "user", "content": [{"type": "text", "text": "hi"}]}
        assert has_multimodal(message) is False

    def test_image_part_is_multimodal(self):
        message = {
            "role": "user",
            "content": [
                {"type": "text", "text": "hi"},
                {"type": "image_url", "image_url": {"url": "x"}},
            ],
        }
        assert has_multimodal(message) is True


class TestMapText:
    def test_maps_string_content(self):
        result = map_text({"role": "user", "content": "hi"}, str.upper)
        assert result == {"role": "user", "content": "HI"}

    def test_does_not_mutate_input(self):
        original = {"role": "user", "content": "hi"}
        map_text(original, str.upper)
        assert original["content"] == "hi"

    def test_maps_text_parts_only(self):
        message = {
            "role": "user",
            "content": [
                {"type": "text", "text": "hi"},
                {"type": "image_url", "image_url": {"url": "x"}},
            ],
        }
        result = map_text(message, str.upper)
        assert result["content"][0] == {"type": "text", "text": "HI"}
        assert result["content"][1] == {"type": "image_url", "image_url": {"url": "x"}}

    def test_none_content_passthrough(self):
        result = map_text({"role": "assistant", "content": None}, str.upper)
        assert result["content"] is None

    def test_preserves_other_keys(self):
        message = {"role": "tool", "content": "result", "tool_call_id": "abc"}
        result = map_text(message, str.upper)
        assert result["tool_call_id"] == "abc"
