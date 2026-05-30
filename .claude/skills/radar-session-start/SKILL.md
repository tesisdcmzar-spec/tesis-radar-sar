---
name: radar-session-start
description: Start a focused session for the radar SAR thesis repo. Use when beginning work or choosing the next task.
disable-model-invocation: true
---

Start a read-only session.

1. Do not edit files.
2. Inspect only project-level context: `git status`, top-level tree, README/CLAUDE.md, configs, and tests if present.
3. Report:
   - current repo state
   - safest next task
   - files likely to touch
   - commands/tests to run
   - hardware risk: none / low / high
4. If the user requested a specific task, scope the plan to that task.
5. Keep the answer concise.
