# Routing evaluation

[`cases.json`](cases.json) contains 20 manually labeled Chinese tasks: seven FAST, seven BALANCED, and six DEEP. The set includes direct explanations of security and concurrency concepts to check that topic keywords alone do not force DEEP. Labels represent the expected routing tier under the current rubric; they are not proof of downstream Codex task quality.

From the router project directory, run:

```bash
.venv/bin/python evals/run.py --config config.toml --output /tmp/jev-router-eval.json
```

The runner uses the production Jev `QUESTION`, task-context builder, and routing policy. It sends each prompt to TypeSafe using `TYPESAFE_API_KEY`, then reports Jev's choice, confidence, the effective tier after the confidence gate, and routing latency. It does not start Codex or execute the tasks. The report is written only when all calls succeed.

## Initial result (2026-09-30)

With the local route configuration (`confidence_threshold = 0.8`), one pass classified all 20 tasks as labeled: 7 FAST, 7 BALANCED, and 6 DEEP. Two BALANCED cases had confidence below the threshold (`0.70` and `0.74`); both remained BALANCED after fallback. Median Jev routing latency was 338 ms. See [`results-2026-09-30.json`](results-2026-09-30.json) for every decision. These cases were written against the current rubric, so this result measures basic tier separation and keyword handling, not performance on unseen tasks or actual Codex task success. Re-run the set after changing the prompt or routing policy.
