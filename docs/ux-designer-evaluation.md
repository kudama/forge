# UX Designer model evaluation

Status: queued for evaluation, not evaluated. Owner: Forge. Captured 2026-10-09.

Tracking: [Forge #32](https://github.com/kudama/forge/issues/32) on the [AI Forge work queue](https://github.com/users/kudama/projects/1).

Source: [Forge Backlog: UX Designer Model Evaluation](https://docs.google.com/document/d/1YtKUVk3zkwnXVx9EWAB5L07DHuKcuwaKpWDxCiYt9M8/edit?tab=t.0#heading=h.m6c3rfjuc472), read 2026-10-09. All substantive requirements from that document are captured below. Its undated “Tonight” note is not a scheduled commitment. The source's statement that no GitHub issue exists is superseded by #32.

## Desired outcome

Select the right model or combination of models for a UX Designer subagent within Forge, working alongside the engineering subagent.

Compare local models that fit the actual current Mac Studio with hosted alternatives. Use Training Atlas and Mike's WordPress themes as representative cases. Compare the same tasks for output quality, hardware requirements, latency and cost.

## Responsibilities

| Role | Before implementation | During implementation and review |
| --- | --- | --- |
| UX Designer | Shape user flows, layouts, interactions and visual direction. | Review the working result and supply actionable design feedback. |
| Engineer | Assess feasibility and technical constraints. | Implement the design and own technical correctness. |
| Forge | Coordinate requirements and evaluate tradeoffs. | Review evidence, resolve disagreements and accept the outcome. |

Model selection does not change task grants or give a designer unrestricted access. Reuse the scoped work-order/controller conventions where applicable.

## Evaluation coverage

| Requirement | What to compare |
| --- | --- |
| User-flow reasoning | Clear paths through a task, missing steps and handling of ambiguity. |
| Screenshot interpretation | Findings grounded in the supplied screen rather than invented UI details. |
| Navigation | Labels, structure, wayfinding and transitions appropriate to the user's goal. |
| Interaction design | Controls, feedback, states, errors and recovery. |
| Visual consistency | Repeated components, spacing, hierarchy and coherent visual direction. |
| Accessibility | Concrete issues and actionable improvements; distinguish screenshot observations from behavior requiring runtime checks. |
| Actionable feedback | Prioritized findings and changes an engineer can implement and verify. |
| Hardware fit, latency and cost | Actual local resource use, response time, hosted usage/cost and operational tradeoffs on the same tasks. |

## Completion criteria

- Shortlist candidate models and run comparable design tasks.
- Review and retain sample outputs for Training Atlas and a WordPress theme.
- Document the preferred model or combination and its tradeoffs.
- Define the UX review and engineering handoff.

At execution time, agree a common rubric and record exact models/runtime settings, actual hardware, task inputs and results. Check current hosted availability/pricing instead of assuming it from past chats. Do not select a winner or numerical quality thresholds in advance.

## Handoff and evidence to produce

The design brief should contain the user goal, flow/layout/interaction proposal, constraints, acceptance checks and open questions. Post-implementation review should link findings to visible evidence and distinguish design changes from technical defects. Record how Forge resolves tradeoffs and how Engineer/Designer responses are reviewed.

Store sanitized evaluation fixtures, outputs, comparison results and the final recommendation under the existing [experiments area](experiments/README.md) when the evaluation runs. Include failure cases and limits. Keep private health records, screenshots containing personal data, credentials and account details outside the public repository. Use synthetic/sanitized examples for hosted evaluations unless the user separately authorizes the relevant disclosure.

## Current state and next action

No candidates were benchmarked by this intake. The next executor should inspect current models/hardware, select a bounded candidate/task set, claim #32 under the [backlog workflow](backlog.md), and run the evaluation. Ready means queued; no automatic dispatch or date was established.

