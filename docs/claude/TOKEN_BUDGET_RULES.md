# Token and usage strategy

Goal: get maximum thesis progress with minimum wasted context.

## Main rule

Keep `CLAUDE.md` short. Put only facts Claude needs in every session. Put procedures in skills or prompt files.

## What should be in CLAUDE.md

- Project scope.
- Environment: Windows + PowerShell.
- Safety boundaries.
- Repository layout.
- Safe commands.
- Data handling rule: never read huge raw arrays directly.

## What should not be in CLAUDE.md

- Long thesis theory.
- Full PDF context.
- Full code explanations.
- Long checklists.
- Full prompt libraries.
- Full experiment logs.

## How to save tokens during real work

1. One task per session.
2. Use file paths instead of pasting whole files.
3. Ask Claude to inspect only the relevant files.
4. Use `/plan` before large edits.
5. Use `/diff` after edits instead of asking for a full restatement.
6. Use `/context all` when the session feels bloated.
7. Use `/compact` after finishing a subtask, with a focused instruction.
8. Use `/clear` when switching to an unrelated task.
9. Use `/usage` often.
10. Do not ask Claude to read `.npy` data. Ask it to create a script that summarizes the dataset.

## English prompts

Use English prompts for Claude Code because the codebase, filenames, Python APIs, and technical terms are naturally English. This may help efficiency, but the bigger savings come from smaller scope, not language alone.

## Chatbot vs Claude Code split

Use a chatbot for: theory, planning, prompt drafting, thesis writing, paper summaries, architecture comparison.

Use Claude Code for: reading the local repo, editing files, running tests, refactoring scripts, generating figures, and updating documentation.

Do not make Claude Code re-research general theory if the chatbot can summarize the exact requirement first.
