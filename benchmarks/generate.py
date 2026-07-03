"""Generate synthetic 50-turn agent transcripts for benchmarking.

No API calls: everything is templated. Each transcript plants 5 recall
facts early on, a fake secret, and a fake email, then buries them under
verbose tool output so compression strategies have something real to cut.
"""

from __future__ import annotations

import json
import random
from pathlib import Path

TRANSCRIPTS_DIR = Path(__file__).parent / "transcripts"

# Deliberately fake, format-only -- see .gitleaks.toml for the allowlist.
FAKE_AWS_KEY = "AKIA" + "X" * 16
FAKE_EMAIL = "sam.reviewer@example.com"

FACT_TEMPLATES = [
    ("The deployment codename is {}.", ["Falcon", "Nimbus", "Orion", "Vega", "Atlas"]),
    ("Budget approved: ${}.", ["42,000", "18,500", "97,250", "63,000", "125,400"]),
    ("Primary contact is {}.", ["Dana Ortiz", "Marcus Webb", "Priya Nair", "Ken Sato"]),
    ("Ticket number: {}.", ["JIRA-4821", "JIRA-5190", "JIRA-6002", "JIRA-7334"]),
    ("We decided to launch on {}.", ["March 3rd", "April 12th", "May 20th", "June 1st"]),
]


def _make_facts(rng: random.Random) -> list:
    facts = []
    for template, options in FACT_TEMPLATES:
        facts.append(template.format(rng.choice(options)))
    return facts


def _make_tool_output(rng: random.Random, turn: int) -> str:
    lines = [
        f"row {i}: id={rng.randint(1000, 9999)} status=ok payload={'x' * 40}" for i in range(40)
    ]
    return f"Search results for query #{turn}:\n" + "\n".join(lines)


def generate_transcript(seed: int, n_turns: int = 50) -> dict:
    """Build one synthetic transcript with planted facts, a secret, and PII."""
    rng = random.Random(seed)
    messages = [{"role": "system", "content": "You are a helpful engineering assistant."}]
    facts = _make_facts(rng)

    for turn in range(n_turns):
        user_content = f"Turn {turn}: please check on the project status."
        if turn < len(facts):
            user_content += " " + facts[turn]
        if turn == 7:
            user_content += f" Also here's my email for follow-up: {FAKE_EMAIL}"
        if turn == 9:
            user_content += f" oh and I found this old key lying around: {FAKE_AWS_KEY}"
        messages.append({"role": "user", "content": user_content})

        if turn % 2 == 0:
            call_id = f"call_{turn}"
            messages.append(
                {
                    "role": "assistant",
                    "content": None,
                    "tool_calls": [
                        {
                            "id": call_id,
                            "function": {
                                "name": "search",
                                "arguments": json.dumps({"q": f"turn {turn}"}),
                            },
                        }
                    ],
                }
            )
            messages.append(
                {
                    "role": "tool",
                    "tool_call_id": call_id,
                    "name": "search",
                    "content": _make_tool_output(rng, turn),
                }
            )
        messages.append({"role": "assistant", "content": f"Turn {turn}: here's an update."})

    return {
        "messages": messages,
        "planted_facts": facts,
        "planted_secrets": [FAKE_AWS_KEY],
        "planted_pii": [FAKE_EMAIL],
    }


def main() -> None:
    TRANSCRIPTS_DIR.mkdir(parents=True, exist_ok=True)
    for i in range(3):
        transcript = generate_transcript(seed=1000 + i, n_turns=50)
        path = TRANSCRIPTS_DIR / f"transcript_{i + 1}.json"
        path.write_text(json.dumps(transcript, indent=2), encoding="utf-8")
        print(f"wrote {path}")


if __name__ == "__main__":
    main()
