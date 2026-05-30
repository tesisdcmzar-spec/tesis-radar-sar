# Claude Code setup for the radar thesis repo

Use this setup from native Windows PowerShell.

## 1. Put these files in your repository

Recommended root:

```powershell
cd C:\path\to\tesis-radar-sar
```

Copy this pack into that folder so the repo contains:

```text
CLAUDE.md
.gitignore
.claude\settings.json
.claude\skills\...
docs\claude\...
```

## 2. Initialize Git locally

```powershell
git init
git add CLAUDE.md .gitignore .claude docs
git commit -m "Add Claude Code operating files"
```

Git can stay local. You do not need GitHub to get rollback checkpoints.

## 3. Start Claude Code

```powershell
claude
```

Inside Claude Code, use:

```text
/status
/memory
/usage
```

`/memory` verifies that `CLAUDE.md` is loaded. `/usage` checks session usage. `/status` checks model, account, version, and connectivity.

## 4. First useful command

```text
/radar-session-start
```

Then work one phase at a time.
