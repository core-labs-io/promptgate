"""Replay synthetic transcripts through each compression strategy.

Outputs a markdown table (tokens before/after, recall-fact survival,
secret/PII catch rate) for the README. Run ``generate.py`` first.
"""

from __future__ import annotations

import json
from pathlib import Path

from promptgate import Gate, formats
from promptgate.counters import count_messages

TRANSCRIPTS_DIR = Path(__file__).parent / "transcripts"
RESULTS_PATH = Path(__file__).parent / "results.md"
BUDGET = 4000
STRATEGIES = ["window", "truncate_tools", "hybrid"]


def _combined_text(messages: list) -> str:
    return "\n".join(formats.get_text(m) for m in messages)


def _run_strategy(transcript: dict, compress: str) -> dict:
    # on_secret="mask" keeps the benchmark run quiet; catch-rate is measured
    # independently below by checking the planted values are gone from output.
    gate = Gate(budget=BUDGET, compress=compress, on_secret="mask")
    messages = transcript["messages"]
    tokens_before = count_messages(messages)
    safe, _pii_map = gate.prepare(messages)
    tokens_after = count_messages(safe)

    facts = transcript["planted_facts"]
    combined = _combined_text(safe)
    facts_survived = sum(1 for fact in facts if fact in combined)
    fact_survival_rate = (facts_survived / len(facts) * 100) if facts else 100.0

    planted = transcript["planted_secrets"] + transcript["planted_pii"]
    caught = sum(1 for value in planted if value not in combined)
    catch_rate = (caught / len(planted) * 100) if planted else 100.0

    percent_saved = ((tokens_before - tokens_after) / tokens_before * 100) if tokens_before else 0.0

    return {
        "tokens_before": tokens_before,
        "tokens_after": tokens_after,
        "percent_saved": percent_saved,
        "fact_survival_rate": fact_survival_rate,
        "catch_rate": catch_rate,
    }


def _average(rows: list, key: str) -> float:
    return sum(r[key] for r in rows) / len(rows)


def main() -> None:
    paths = sorted(TRANSCRIPTS_DIR.glob("*.json"))
    if not paths:
        print("No transcripts found. Run `python benchmarks/generate.py` first.")
        return

    transcripts = [json.loads(p.read_text(encoding="utf-8")) for p in paths]

    lines = [
        f"Benchmark: {len(transcripts)} synthetic 50-turn agent transcripts, "
        f"budget={BUDGET:,} tokens.\n",
        "| Strategy | Tokens before -> after | % saved | Recall-facts surviving | "
        "Secrets/PII caught |",
        "|---|---|---|---|---|",
    ]

    for strategy in STRATEGIES:
        rows = [_run_strategy(t, strategy) for t in transcripts]
        avg_before = _average(rows, "tokens_before")
        avg_after = _average(rows, "tokens_after")
        avg_saved = _average(rows, "percent_saved")
        avg_fact = _average(rows, "fact_survival_rate")
        avg_catch = _average(rows, "catch_rate")
        lines.append(
            f"| {strategy} | {avg_before:,.0f} -> {avg_after:,.0f} | {avg_saved:.0f}% | "
            f"{avg_fact:.0f}% | {avg_catch:.0f}% |"
        )

    output = "\n".join(lines)
    print(output)
    RESULTS_PATH.write_text(output + "\n", encoding="utf-8")


if __name__ == "__main__":
    main()
