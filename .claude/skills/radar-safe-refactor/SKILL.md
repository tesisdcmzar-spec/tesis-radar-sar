---
name: radar-safe-refactor
description: Conservatively refactor one working radar script while preserving behavior and hardware parameters.
argument-hint: "<target-file>"
disable-model-invocation: true
---

Target: $ARGUMENTS

Refactor conservatively.

Process:
1. Read the target file and identify RF/motor parameters, timing, buffers, metadata, and outputs.
2. Explain the current behavior briefly.
3. Propose a minimal refactor plan.
4. Only edit after the user approves, unless the user already explicitly requested edits.
5. Preserve behavior, filenames, output shapes, metadata, and hardware parameters.
6. Add small tests or smoke checks when possible.
7. Show a concise diff summary.

Never run RF transmission, motor movement, firmware upload, or full scans.
