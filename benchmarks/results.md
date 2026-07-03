Benchmark: 3 synthetic 50-turn agent transcripts, budget=4,000 tokens.

| Strategy | Tokens before -> after | % saved | Recall-facts surviving | Secrets/PII caught |
|---|---|---|---|---|
| window | 27,322 -> 3,330 | 88% | 0% | 100% |
| truncate_tools | 27,322 -> 2,596 | 90% | 100% | 100% |
| hybrid | 27,322 -> 2,596 | 90% | 100% | 100% |
