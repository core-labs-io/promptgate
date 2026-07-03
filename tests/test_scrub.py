import pytest

from promptgate.scrub import Scrubber, SecretFound

# All values below are deliberately fake / format-only — obviously not live
# credentials, so the repo passes a gitleaks scan cleanly.
FAKE_ANTHROPIC_KEY = "sk-ant-" + "x" * 12
FAKE_OPENAI_KEY = "sk-" + "x" * 25
FAKE_AWS_KEY = "AKIA" + "X" * 16
FAKE_GITHUB_TOKEN = "ghp_" + "x" * 25
FAKE_SLACK_TOKEN = "xoxb-" + "x" * 15
FAKE_GOOGLE_KEY = "AIza" + "x" * 35
FAKE_STRIPE_KEY = "sk_live_" + "x" * 25
FAKE_JWT = "eyJhbGciOiJIUzI1NiJ9.eyJzdWIiOiJ0ZXN0In0.fakesignaturevalue"
FAKE_BEARER_BLOB = "x" * 20
FAKE_PEM_BLOCK = (
    "-----BEGIN RSA PRIVATE KEY-----\n"
    "MIIFAKEKEYDATANOTREALXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXX\n"
    "-----END RSA PRIVATE KEY-----"
)
FAKE_ENTROPY_STRING = "aZ3kQ9mN2pX7vB5cL8fD1sW4hT6gY0j"


class TestPEM:
    def test_pem_block_masked_atomically(self):
        scrubber = Scrubber()
        text, report, _ = scrubber.scrub_text(f"key:\n{FAKE_PEM_BLOCK}\ndone")
        assert "-----BEGIN" not in text
        assert "MIIFAKEKEYDATA" not in text
        assert "[[SECRET_PEM_1]]" in text
        assert len(report.secrets) == 1

    def test_pem_not_half_masked(self):
        scrubber = Scrubber()
        text, _, _ = scrubber.scrub_text(FAKE_PEM_BLOCK)
        # exactly one placeholder token represents the whole block
        assert text.count("[[SECRET_PEM_1]]") == 1
        assert text == "[[SECRET_PEM_1]]"


class TestPrefixPatterns:
    @pytest.mark.parametrize(
        "value,expected_category",
        [
            (FAKE_ANTHROPIC_KEY, "ANTHROPIC"),
            (FAKE_OPENAI_KEY, "OPENAI"),
            (FAKE_AWS_KEY, "AWS"),
            (FAKE_GITHUB_TOKEN, "GITHUB"),
            (FAKE_SLACK_TOKEN, "SLACK"),
            (FAKE_GOOGLE_KEY, "GOOGLE"),
            (FAKE_STRIPE_KEY, "STRIPE"),
            (FAKE_JWT, "JWT"),
        ],
    )
    def test_known_prefix_detected_and_masked(self, value, expected_category):
        scrubber = Scrubber()
        text, report, _ = scrubber.scrub_text(f"here is a key: {value} end")
        assert value not in text
        assert f"[[SECRET_{expected_category}_1]]" in text
        assert any(s.category == expected_category for s in report.secrets)

    def test_anthropic_matched_before_openai(self):
        scrubber = Scrubber()
        text, report, _ = scrubber.scrub_text(FAKE_ANTHROPIC_KEY)
        assert "[[SECRET_ANTHROPIC_1]]" in text
        assert "OPENAI" not in text
        assert report.secrets[0].category == "ANTHROPIC"

    def test_bearer_token_preserves_prefix(self):
        scrubber = Scrubber()
        text, _, _ = scrubber.scrub_text(f"Authorization: Bearer {FAKE_BEARER_BLOB}")
        assert FAKE_BEARER_BLOB not in text
        assert "Bearer [[SECRET_BEARER_1]]" in text


class TestContextKeywords:
    def test_password_assignment_masks_value_keeps_prefix(self):
        scrubber = Scrubber()
        text, report, _ = scrubber.scrub_text("password=SuperSecretXXXX123")
        assert "SuperSecretXXXX123" not in text
        assert text.startswith("password=[[SECRET_CREDENTIAL_1]]")
        assert report.secrets[0].category == "CREDENTIAL"

    def test_api_key_colon_form(self):
        scrubber = Scrubber()
        text, _, _ = scrubber.scrub_text("api_key: abcdef123456XYZ")
        assert "abcdef123456XYZ" not in text
        assert "api_key:[[SECRET_CREDENTIAL_1]]" in text

    def test_connection_string_password_masked(self):
        scrubber = Scrubber()
        text, report, _ = scrubber.scrub_text(
            "postgres://user:PASSWORDXXXX123@localhost:5432/db"
        )
        assert "PASSWORDXXXX123" not in text
        assert "postgres://user:[[SECRET_CREDENTIAL_1]]@localhost:5432/db" == text


class TestEntropy:
    def test_disabled_by_default(self):
        scrubber = Scrubber()
        text, report, _ = scrubber.scrub_text(FAKE_ENTROPY_STRING)
        assert FAKE_ENTROPY_STRING in text
        assert report.secrets == []

    def test_enabled_detects_high_entropy_string(self):
        scrubber = Scrubber(entropy_threshold=3.0)
        text, report, _ = scrubber.scrub_text(f"random value {FAKE_ENTROPY_STRING} end")
        assert FAKE_ENTROPY_STRING not in text
        assert any(s.category == "HIGH_ENTROPY" for s in report.secrets)

    def test_short_strings_never_flagged(self):
        scrubber = Scrubber(entropy_threshold=0.0)
        text, _, _ = scrubber.scrub_text("short")
        assert text == "short"


class TestOnSecretBehavior:
    def test_mask_is_silent(self, capsys):
        scrubber = Scrubber(on_secret="mask")
        scrubber.scrub_text(FAKE_AWS_KEY)
        captured = capsys.readouterr()
        assert captured.err == ""

    def test_warn_writes_to_stderr_without_value(self, capsys):
        scrubber = Scrubber(on_secret="warn")
        scrubber.scrub_text(FAKE_AWS_KEY)
        captured = capsys.readouterr()
        assert "rotate" in captured.err.lower()
        assert FAKE_AWS_KEY not in captured.err

    def test_warn_uses_callback_when_given(self):
        messages = []
        scrubber = Scrubber(on_secret="warn", warn_callback=messages.append)
        scrubber.scrub_text(FAKE_AWS_KEY)
        assert len(messages) == 1
        assert FAKE_AWS_KEY not in messages[0]

    def test_raise_raises_secret_found(self):
        scrubber = Scrubber(on_secret="raise")
        with pytest.raises(SecretFound) as exc_info:
            scrubber.scrub_text(FAKE_AWS_KEY)
        assert FAKE_AWS_KEY not in str(exc_info.value)

    def test_raise_exception_message_has_no_value(self):
        scrubber = Scrubber(on_secret="raise")
        try:
            scrubber.scrub_text(f"key is {FAKE_ANTHROPIC_KEY}")
        except SecretFound as exc:
            assert FAKE_ANTHROPIC_KEY not in str(exc)
            assert FAKE_ANTHROPIC_KEY not in repr(exc)


class TestPII:
    def test_email_masked_and_reversible(self):
        scrubber = Scrubber(categories=["email"])
        text, report, pii_map = scrubber.scrub_text("contact bob@example.com now")
        assert "bob@example.com" not in text
        assert "[[EMAIL_1]]" in text
        assert pii_map["[[EMAIL_1]]"] == "bob@example.com"
        assert report.pii_counts["EMAIL"] == 1

    def test_phone_masked(self):
        scrubber = Scrubber(categories=["phone"])
        text, _, pii_map = scrubber.scrub_text("call 415-555-0199 today")
        assert "415-555-0199" not in text
        assert "[[PHONE_1]]" in text
        assert pii_map["[[PHONE_1]]"] == "415-555-0199"

    def test_ssn_masked(self):
        scrubber = Scrubber(categories=["ssn"])
        text, _, pii_map = scrubber.scrub_text("ssn: 123-45-6789")
        assert "123-45-6789" not in text
        assert pii_map["[[SSN_1]]"] == "123-45-6789"

    def test_credit_card_masked(self):
        scrubber = Scrubber(categories=["credit_card"])
        text, _, pii_map = scrubber.scrub_text("card 4111 1111 1111 1111 exp 12/30")
        assert "4111 1111 1111 1111" not in text
        assert pii_map["[[CREDIT_CARD_1]]"] == "4111 1111 1111 1111"

    def test_ip_masked(self):
        scrubber = Scrubber(categories=["ip"])
        text, _, pii_map = scrubber.scrub_text("server at 192.168.1.1 responded")
        assert "192.168.1.1" not in text
        assert pii_map["[[IP_1]]"] == "192.168.1.1"

    def test_same_value_reuses_placeholder_within_call(self):
        scrubber = Scrubber(categories=["email"])
        text, _, pii_map = scrubber.scrub_text("bob@example.com and again bob@example.com")
        assert text.count("[[EMAIL_1]]") == 2
        assert len(pii_map) == 1

    def test_distinct_values_get_distinct_placeholders(self):
        scrubber = Scrubber(categories=["email"])
        text, _, pii_map = scrubber.scrub_text("bob@example.com and alice@example.com")
        assert "[[EMAIL_1]]" in text
        assert "[[EMAIL_2]]" in text
        assert len(pii_map) == 2

    def test_pii_map_continuity_across_calls(self):
        scrubber = Scrubber(categories=["email"])
        _, _, pii_map = scrubber.scrub_text("bob@example.com")
        text2, _, pii_map2 = scrubber.scrub_text("bob@example.com and carol@example.com", pii_map)
        assert "[[EMAIL_1]]" in text2  # bob keeps his placeholder
        assert "[[EMAIL_2]]" in text2  # carol gets a fresh one
        assert len(pii_map2) == 2

    def test_category_not_configured_is_left_alone(self):
        scrubber = Scrubber(categories=["phone"])
        text, report, _ = scrubber.scrub_text("bob@example.com")
        assert text == "bob@example.com"
        assert report.pii_counts == {}


class TestCategoryFiltering:
    def test_secrets_only_leaves_pii_untouched(self):
        scrubber = Scrubber(categories=["secrets"])
        text, _, pii_map = scrubber.scrub_text(f"{FAKE_AWS_KEY} and bob@example.com")
        assert FAKE_AWS_KEY not in text
        assert "bob@example.com" in text
        assert pii_map == {}

    def test_pii_only_leaves_secrets_untouched(self):
        scrubber = Scrubber(categories=["email"])
        text, report, _ = scrubber.scrub_text(f"{FAKE_AWS_KEY} and bob@example.com")
        assert FAKE_AWS_KEY in text
        assert "bob@example.com" not in text
        assert report.secrets == []


class TestIdempotency:
    def test_scrubbing_twice_equals_scrubbing_once(self):
        scrubber = Scrubber(categories=["secrets", "email", "phone", "ssn", "ip"])
        original = (
            f"{FAKE_AWS_KEY} password=hunterXXXX123 bob@example.com "
            "415-555-0199 192.168.1.1"
        )
        once, _, _ = scrubber.scrub_text(original)
        twice, report2, _ = scrubber.scrub_text(once)
        assert once == twice
        assert report2.secrets == []
        assert report2.pii_counts == {}

    def test_pem_idempotent(self):
        scrubber = Scrubber()
        once, _, _ = scrubber.scrub_text(FAKE_PEM_BLOCK)
        twice, _, _ = scrubber.scrub_text(once)
        assert once == twice


class TestScrubMessages:
    def test_scrubs_across_messages_with_shared_map(self):
        scrubber = Scrubber(categories=["email"])
        messages = [
            {"role": "user", "content": "I am bob@example.com"},
            {"role": "assistant", "content": "got it, bob@example.com noted"},
        ]
        new_messages, _, pii_map = scrubber.scrub_messages(messages)
        assert "[[EMAIL_1]]" in new_messages[0]["content"]
        assert "[[EMAIL_1]]" in new_messages[1]["content"]
        assert len(pii_map) == 1

    def test_preserves_non_content_fields(self):
        scrubber = Scrubber(categories=["email"])
        messages = [{"role": "tool", "content": "bob@example.com", "tool_call_id": "call_1"}]
        new_messages, _, _ = scrubber.scrub_messages(messages)
        assert new_messages[0]["tool_call_id"] == "call_1"

    def test_multimodal_parts_pass_through(self):
        scrubber = Scrubber(categories=["email"])
        messages = [
            {
                "role": "user",
                "content": [
                    {"type": "text", "text": "bob@example.com"},
                    {"type": "image_url", "image_url": {"url": "https://x/y.png"}},
                ],
            }
        ]
        new_messages, _, _ = scrubber.scrub_messages(messages)
        parts = new_messages[0]["content"]
        assert parts[0]["text"] == "[[EMAIL_1]]"
        assert parts[1] == {"type": "image_url", "image_url": {"url": "https://x/y.png"}}

    def test_does_not_mutate_input_messages(self):
        scrubber = Scrubber(categories=["email"])
        messages = [{"role": "user", "content": "bob@example.com"}]
        scrubber.scrub_messages(messages)
        assert messages[0]["content"] == "bob@example.com"


class TestInvalidConfig:
    def test_invalid_on_secret_raises(self):
        with pytest.raises(ValueError):
            Scrubber(on_secret="bogus")
