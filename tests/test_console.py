import sys

from promptgate._console import supports_unicode


class _FakeStream:
    def __init__(self, encoding):
        self.encoding = encoding


class TestSupportsUnicode:
    def test_true_for_utf8_streams(self, monkeypatch):
        monkeypatch.setattr(sys, "stdout", _FakeStream("utf-8"))
        monkeypatch.setattr(sys, "stderr", _FakeStream("utf-8"))
        assert supports_unicode() is True

    def test_false_when_stdout_cannot_encode(self, monkeypatch):
        monkeypatch.setattr(sys, "stdout", _FakeStream("cp1252"))
        monkeypatch.setattr(sys, "stderr", _FakeStream("utf-8"))
        assert supports_unicode() is False

    def test_false_when_stderr_cannot_encode(self, monkeypatch):
        monkeypatch.setattr(sys, "stdout", _FakeStream("utf-8"))
        monkeypatch.setattr(sys, "stderr", _FakeStream("cp1252"))
        assert supports_unicode() is False

    def test_false_on_unknown_encoding_name(self, monkeypatch):
        monkeypatch.setattr(sys, "stdout", _FakeStream("not-a-real-encoding"))
        monkeypatch.setattr(sys, "stderr", _FakeStream("utf-8"))
        assert supports_unicode() is False

    def test_missing_encoding_attr_falls_back_to_utf8(self, monkeypatch):
        monkeypatch.setattr(sys, "stdout", object())
        monkeypatch.setattr(sys, "stderr", object())
        assert supports_unicode() is True
