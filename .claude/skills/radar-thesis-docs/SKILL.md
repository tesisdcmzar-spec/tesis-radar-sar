---
name: radar-thesis-docs
description: Turn experiment logs, figures, and code results into thesis-ready Spanish technical text with careful claims.
argument-hint: "<log-or-results-path>"
disable-model-invocation: true
---

Input: $ARGUMENTS

Draft thesis material in Spanish.

Rules:
1. State only what is supported by simulation, phantom, or measured data.
2. Do not claim clinical diagnosis.
3. Separate method, result, interpretation, limitation, and next work.
4. Include figure/table placeholders when useful.
5. Mention reproducibility: config, metadata, script version, and dataset provenance.
6. Keep text formal and thesis-ready.
