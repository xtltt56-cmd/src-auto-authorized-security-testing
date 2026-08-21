---
name: src-orchestrator
description: Run the checkpointed SRC-Auto workflow with policy and resource gates.
---

# SRC Orchestrator

Before every stage, check ScopeGuard, disk, resource, budget, and STOP. Prefer local fixtures. External adapters must be invoked without shell interpolation and only with URLs that passed the confirmed scope guard.
