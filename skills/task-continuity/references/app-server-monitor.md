# App Server threshold monitor

Use this reference only when integrating automatic threshold activation. Manual
`$task-continuity checkpoint` and resume mode do not need the monitor.

## Boundary

`continuity_watch.py` is a JSONL protocol component, not a background attachment
for the stock Codex TUI. An App Server client or wrapper must:

1. start or connect to Codex App Server;
2. send `account/rateLimits/read` at startup and forward the returned snapshots
   as an `account/rateLimits/updated`-shaped message;
3. forward `account/rateLimits/updated`, `thread/tokenUsage/updated`,
   `turn/started`, `turn/completed`, and context-compaction `item/completed`
   notifications to the watcher;
4. send emitted `turn/start` requests back to the same App Server;
5. preserve normal request/response routing for the primary client.

The watcher does not poll. Rate-limit notifications can be sparse, so it caches
the latest window metadata and merges later updates. The initial read prevents a
sparse first update from being ambiguous.

## Thresholds

- Rate limit: select a window with `windowDurationMins == 300`; trigger when
  `100 - usedPercent <= 10`.
- Context: for `thread/tokenUsage/updated`, trigger when
  `(modelContextWindow - last.totalTokens) / modelContextWindow * 100 <= 15`.

The watcher waits for an active turn to complete, then emits one checkpoint
request. It deduplicates a rate trigger by quota window and a context trigger by
thread. Context re-arms after usage rises above the threshold or a context
compaction item is observed.

## Invocation

To emit portable action records:

```bash
python3 scripts/continuity_watch.py \
  --state-file .codex/task-continuity-watch.json
```

To emit App Server `turn/start` requests that explicitly invoke the skill:

```bash
python3 scripts/continuity_watch.py \
  --output-mode turn-start \
  --skill-path /absolute/path/to/task-continuity/SKILL.md \
  --thread-id THREAD_ID \
  --state-file .codex/task-continuity-watch.json
```

The state file contains only deduplication metadata and should remain local. It
does not contain credentials or transcript content.
