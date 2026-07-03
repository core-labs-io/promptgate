from promptgate.report import ExplainReport
from promptgate.scrub import SecretFound


class TestTokenMath:
    def test_tokens_saved(self):
        report = ExplainReport(tokens_before=100, tokens_after=40)
        assert report.tokens_saved == 60

    def test_percent_saved(self):
        report = ExplainReport(tokens_before=200, tokens_after=100)
        assert report.percent_saved == 50.0

    def test_percent_saved_zero_before_is_zero_not_divide_error(self):
        report = ExplainReport(tokens_before=0, tokens_after=0)
        assert report.percent_saved == 0.0

    def test_negative_saved_when_grows(self):
        report = ExplainReport(tokens_before=100, tokens_after=120)
        assert report.tokens_saved == -20


class TestSecretsSummary:
    def test_no_secrets(self):
        report = ExplainReport(tokens_before=10, tokens_after=10)
        assert report._secrets_summary() == "none found"

    def test_single_secret(self):
        report = ExplainReport(
            tokens_before=10, tokens_after=10, secrets=[SecretFound("AWS", "AWS Access Key")]
        )
        assert report._secrets_summary() == "1 AWS key BLOCKED (one-way)"

    def test_multiple_of_same_category(self):
        report = ExplainReport(
            tokens_before=10,
            tokens_after=10,
            secrets=[SecretFound("AWS", "AWS Access Key"), SecretFound("AWS", "AWS Access Key")],
        )
        assert report._secrets_summary() == "2 AWS keys BLOCKED (one-way)"

    def test_multiple_categories(self):
        report = ExplainReport(
            tokens_before=10,
            tokens_after=10,
            secrets=[SecretFound("AWS", "AWS Access Key"), SecretFound("GITHUB", "GitHub Token")],
        )
        summary = report._secrets_summary()
        assert "1 AWS key" in summary
        assert "1 GitHub token" in summary
        assert summary.endswith("BLOCKED (one-way)")

    def test_unknown_category_falls_back_gracefully(self):
        report = ExplainReport(
            tokens_before=10, tokens_after=10, secrets=[SecretFound("MYSTERY", "Mystery Secret")]
        )
        assert "mystery" in report._secrets_summary()


class TestPiiSummary:
    def test_no_pii(self):
        report = ExplainReport(tokens_before=10, tokens_after=10)
        assert report._pii_summary() == "none found"

    def test_pluralization(self):
        report = ExplainReport(tokens_before=10, tokens_after=10, pii_counts={"EMAIL": 3})
        assert report._pii_summary() == "3 emails masked (reversible)"

    def test_singular(self):
        report = ExplainReport(tokens_before=10, tokens_after=10, pii_counts={"PHONE": 1})
        assert report._pii_summary() == "1 phone masked (reversible)"

    def test_ip_address_pluralization(self):
        report = ExplainReport(tokens_before=10, tokens_after=10, pii_counts={"IP": 2})
        assert "2 IP addresses" in report._pii_summary()


class TestStr:
    def test_matches_hero_block_shape(self):
        report = ExplainReport(
            tokens_before=11840,
            tokens_after=5210,
            secrets=[SecretFound("AWS", "AWS Access Key")],
            pii_counts={"EMAIL": 3, "PHONE": 1},
            structure_valid=True,
        )
        text = str(report)
        lines = text.splitlines()
        assert lines[0] == "promptgate report"
        assert "11,840" in lines[2]
        assert "5,210" in lines[2]
        assert "56%" in lines[2]
        assert "AWS key BLOCKED (one-way)" in lines[3]
        assert "3 emails, 1 phone masked (reversible)" in lines[4]
        assert "valid" in lines[5]

    def test_invalid_structure_shown(self):
        report = ExplainReport(tokens_before=10, tokens_after=10, structure_valid=False)
        assert "INVALID" in str(report)

    def test_warnings_appended(self):
        report = ExplainReport(
            tokens_before=10, tokens_after=10, warnings=["single message exceeds budget"]
        )
        text = str(report)
        assert "single message exceeds budget" in text
