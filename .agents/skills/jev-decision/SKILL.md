---
name: jev-decision
description: >
  Use the Jev decision MCP for fast, large-scale, homogeneous semantic
  judgments: apply one shared Choice, Noul, or Score definition independently to
  many items for classification, filtering, labeling, scoring, routing,
  verification, or prioritization. Also use a single bounded judgment when typed
  probabilities directly control automation versus review. Do not use for exact
  calculations or lookups, evidence gathering, open-ended generation, dependent
  multi-step reasoning, or ordinary one-off questions where structured
  probabilities provide no workflow value.
---

# Jev Decision

Use TypeSafe as a high-throughput semantic judgment primitive, not as a substitute
for Codex reasoning. The user only describes the task; do not require them to
mention TypeSafe, MCP, tool names, primitives, thresholds, or response fields.

## Decide whether to call

Make this meta-decision locally. Never call TypeSafe to decide whether to call
TypeSafe. Trigger primarily from the shape of the work, not its business domain.

Use the MCP when all of these hold:

- the work is semantic rather than exactly computable;
- the answer type and criteria can be stated before inference;
- the relevant input facts are already available;
- several independent items share the same judgment, or the judgment will recur;
- typed answers or probabilities can be consumed without generating explanations.

The strongest signal is a collection of independent items that can share one
question template. Domain, urgency, and severity are not routing criteria. Do not
call for deterministic work, research, missing evidence, prose generation,
cross-item synthesis, or sequential judgments where an earlier answer changes the
state or options for a later one. For a single item, call only when its probability
distribution changes an explicit automation, review, or clarification branch.

The judgment tools send their `state` and question definitions to the external
TypeSafe API. Never include credentials, secrets, or irrelevant repository content.
Do not invoke them implicitly for content that appears confidential unless the user
has authorized external processing; continue locally or ask before transmitting it.

An explicit invocation of this skill overrides the ordinary value gate and requests
an MCP-backed judgment unless doing so would be invalid or unsafe.

## Choose the tool

Use `jev_decision.jev_judge_batch` when many items share one judgment:

- put each independent input in an item with a stable id;
- define one shared Choice, Noul, or Score question;
- use Choice for mutually exclusive labels, Noul for a condition probability, and
  Score for a graded rubric;
- keep batches within the tool limits and split only when the schema or relevant
  context differs.

The batch tool performs one TypeSafe request and returns one typed answer per item.
It does not apply actions or invent explanations.

Use `jev_decision.jev_decide` for one bounded action selection whose
confidence or blocker judgments control downstream routing.

## Make a single decision

When calling the tool:

1. Put only relevant observed facts in `state`; keep inferred facts distinct.
2. Use one narrow Choice as the action question. Include `no_action` and
   `needs_clarification` when either may be valid.
3. Add Noul or Score questions only when their answers change routing or safety.
4. Batch independent questions over the same state into one call.
5. Use `review_if_noul_at_least` for conditions that block automatic action.
6. Choose `advisory`, `reversible`, or `consequential` from the actual effect of
   the downstream action, not from how difficult the question sounds.

Normally call the selected tool once. If input validation or a transient service
failure occurs, correct it and retry once unless the user prohibited retries. Do
not replace a failed call with a fabricated TypeSafe result.

## Consume the result

- `decided`: use the returned `action` within the user's existing authorization.
- `uncertain`: clarify, gather evidence, or use deeper reasoning.
- `review_required`: do not automatically take the consequential action.

For batch results, preserve item ids and typed answers; apply any requested
threshold or review policy in code. Preserve probabilities when they matter to the
workflow. Do not invent a rationale that TypeSafe did not return, and do not expose
MCP mechanics unless the user asks or they are needed to explain a failure.
