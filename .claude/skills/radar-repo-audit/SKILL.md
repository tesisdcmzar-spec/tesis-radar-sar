---
name: radar-repo-audit
description: Audit the radar thesis repository structure and propose an efficient modular layout. Use for repository cleanup before coding.
disable-model-invocation: true
---

Perform a read-only repository audit.

Output:
1. Current structure summary.
2. Existing working scripts and probable purpose.
3. Proposed target layout.
4. Minimal move/refactor plan.
5. Risks: broken imports, lost hardware parameters, missing metadata, large data files.
6. Next three safe commits.

Rules:
- Do not edit files unless the user approves after the audit.
- Do not read raw datasets.
- Preserve working scripts before refactor.
