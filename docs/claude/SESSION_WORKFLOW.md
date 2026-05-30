# Recommended Claude Code session workflow

## Before starting Claude Code

```powershell
cd C:\path\to\tesis-radar-sar
git status
git add .
git commit -m "Checkpoint before Claude Code session"
claude
```

If there are files you do not want committed, skip `git add .` and commit only the safe ones.

## At the start of a session

```text
/status
/memory
/usage
/radar-session-start
```

## During a session

Use one objective at a time:

```text
/plan Refactor the existing RX script into a small capture function without changing hardware parameters.
```

After edits:

```text
/diff
```

Then run tests or safe scripts:

```text
Run only safe tests: python -m pytest. Do not run hardware scripts.
```

## Before switching tasks

```text
/compact Summarize only the completed task, changed files, test results, and next step.
```

For unrelated work:

```text
/clear
```

## End of session

```text
/radar-session-close
```

Then in PowerShell:

```powershell
git status
git diff
git add .
git commit -m "Describe completed thesis task"
```
