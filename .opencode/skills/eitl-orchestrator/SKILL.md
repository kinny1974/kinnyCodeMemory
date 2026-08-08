---
name: eitl-orchestrator
description: Orchestrates the EitL pipeline sequence with context protection and automatic batch mode.
---

# EitL Orchestrator

## Sequence
1. scrum-master receives requirement
2. scrum-master delegates to product-owner (generates 01_Plan_Scrum.md)
3. validator validates Gate 1
4. If approved: scrum-master delegates to architect (generates 02_Arquitectura_SDD.md)
5. validator validates Gate 2
6. If approved: scrum-master delegates to tdd-engineer (generates 03_Plan_TDD.md)
7. validator validates Gate 3
8. Pipeline ready for implementation

## Context rules
- BEFORE each delegation, invoke: context-guard({ action: "check", agent: "[target]" })
- If context > 70% for architect, > 75% for tdd-engineer: compact first
- If previous artifact > 300 lines: activate batch-workflow skill

## YOLO mode
- Max 3 retries per gate
- If 3 rejections: escalate to human user
- Zero-second pause between phases (no confirmation)
- Context verified automatically between each phase
