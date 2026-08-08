---
name: context-guard
description: Monitors context window usage for EitL pipeline agents and recommends compaction.
---

## When to invoke
- Before any pipeline stage: /start-SDD, /start-TDD, /start-IMPL
- Before regeneration: /regen
- During status checks: /status
- When switching agents
- When user mentions slowness, hallucinations, or truncated responses

## Agent thresholds
| Agent | Safe | Critical |
|-------|------|----------|
| scrum-master | 65% | 80% |
| product-owner | 60% | 75% |
| architect | 55% | 70% |
| tdd-engineer | 60% | 78% |
| validator | 65% | 80% |
| test-runner | 60% | 75% |
| qa-engineer | 60% | 75% |
| performance-engineer | 55% | 70% |

## Rules
- Never proceed with /start-IMPL if context > 70%
- Always preserve last system prompt and last 3 user messages
- Report exact token counts and percentages
- If session.compact() unavailable, advise /compact in TUI or restart
