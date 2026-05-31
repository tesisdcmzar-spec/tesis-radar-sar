---
name: radar-reading-guide
description: Creates a human reading roadmap for the Radar SAR thesis repo. Use when the user has generated many reports, session logs, thesis drafts, figures, or commits without reading them and wants to know what to read first, what to skim, what to review deeply, what to send to teammates, and what order supports understanding the current project state. Read-only by default. Never modifies radar code or hardware.
disable-model-invocation: true
---

# `/radar-reading-guide` — Human Reading Roadmap for Radar SAR Thesis

## Purpose

Build a prioritized reading plan for the user and teammates.

The skill assumes the user may not have read recent Claude Code outputs. It must inspect the repository documentation and produce an ordered, practical reading roadmap.

It must answer:

* What should the user read first?
* What can be skimmed?
* What must be reviewed deeply before the next phase?
* What should teammates read?
* Which files are engineering logs vs thesis chapters?
* Which files are current and which are historical/context only?
* What questions should the reader answer after each document?

## Read-only rule

This skill is read-only by default.

Allowed commands:

```powershell
git status
git log --oneline -15
git diff --stat
dir reports\session_reports
dir thesis
dir reports\generated
dir docs
dir .claude\skills
```

Allowed files to read if they exist:

```text
README.md
CLAUDE.md
reports/ai_session_log.md
reports/session_reports/*.md
thesis/*.md
docs/**/*.md
.claude/skills/*/SKILL.md
```

Do not:

* run hardware scripts;
* transmit RF;
* move motors;
* import or call bladeRF APIs;
* run long analysis scripts;
* modify code;
* modify reports;
* modify thesis chapters;
* commit or push;
* delete files.

## Document classification

Classify each relevant document into one of these categories:

1. `session_log`

   * Example: `reports/ai_session_log.md`
   * Purpose: chronological map of what happened.

2. `engineering_report`

   * Example: files in `reports/session_reports/`
   * Purpose: technical traceability: what was done, why, commands, tests, errors, limitations.

3. `thesis_chapter`

   * Example: files in `thesis/`
   * Purpose: academic text intended for the final thesis.

4. `operational_guide`

   * Example: `CLAUDE.md`, `README.md`, docs under `docs/`, skill files.
   * Purpose: how to work with the repo and Claude Code.

5. `generated_artifact`

   * Example: figures under `reports/generated/`
   * Purpose: visual outputs to inspect after reading the related report.

6. `historical_context`

   * Older or superseded files that are useful but not first-priority.

## Reading order logic

Build the reading order according to this priority:

### Priority 1 — Project map

Read first:

* `README.md`
* `reports/ai_session_log.md`

Reason:
The user needs the global project state and chronological overview before reading details.

### Priority 2 — Latest phase closure

Read the most recent phase closure report first, especially:

* `reports/session_reports/2026-05-31_phase2_offline_closure.md`
* or the newest file matching `*closure*.md`
* or the latest session report if no closure report exists.

Reason:
This tells the user what is currently considered done, what is not done, and what the next phase is.

### Priority 3 — Supporting engineering reports

Read reports that explain the technical chain leading to the latest closure:

* loader reports;
* simulation reports;
* retrospective reports;
* session-close reports.

Reason:
These explain how the current state was reached.

### Priority 4 — Thesis chapters

Read thesis chapters after understanding the engineering reports:

* theoretical framework;
* simulation chapter;
* offline validation chapter;
* acquisition chapter.

Reason:
Thesis chapters should be reviewed for academic narrative, not for raw debugging history.

### Priority 5 — Figures and generated artifacts

Read/inspect figures after the related report or chapter:

* range profiles;
* SAR images;
* frequency response;
* window comparison.

Reason:
Figures only make sense after the method is understood.

### Priority 6 — Team delegation

Generate a teammate-specific reading list:

* DSP teammate;
* hardware teammate;
* thesis writing teammate;
* project manager / general reviewer.

## Required output format

Always respond in this structure:

```markdown
# Reading Roadmap — Radar SAR Thesis

## 1. Current repo/documentation status

Brief summary of documents found and most recent commits.

## 2. Read this first

Ordered list with:
- file path
- estimated reading time
- why it matters
- what to pay attention to

## 3. Deep review required

Documents the user must read carefully before the next phase.

## 4. Skim only

Documents useful for context but not urgent.

## 5. Thesis chapters to review

Ordered list of thesis chapter drafts, including:
- what the chapter is for
- whether it is current, draft, or potentially duplicated
- warnings such as duplicate chapter numbers

## 6. Reports to send teammates

Split by role:
- DSP / processing
- hardware / bladeRF
- mechanics / azimuth
- thesis writing / documentation
- general project review

## 7. Figures to inspect

List figures and which report/chapter explains each one.

## 8. Questions to answer while reading

Checklist of concrete questions the user should answer.

## 9. Suggested next reading session

A 30–60 minute reading plan.
```

## Special rules

* If two thesis files appear to use the same chapter number, flag it clearly.
* If an engineering report says a phase is closed, verify whether `ai_session_log.md` also reflects it.
* If figures are gitignored, say they may exist only locally and can be regenerated.
* If a file appears superseded by a newer closure report, mark it as historical.
* Never claim the user has read a document.
* Never assume generated figures exist in the current clone unless the repo tracks them.
* Keep the output practical. The user is overwhelmed and needs an ordered plan.

## Recommended first roadmap for the current repo

If the current repo contains the known offline closure files, recommend this order:

1. `reports/ai_session_log.md`
2. `reports/session_reports/2026-05-31_phase2_offline_closure.md`
3. `thesis/cap4_validacion_offline_legacy.md`
4. `reports/session_reports/2026-05-31_phase2_sfcw_loader.md`
5. `reports/session_reports/2026-05-30_simulation_pipeline_resolution_and_thesis_draft.md`
6. `thesis/cap3_simulacion.md`
7. `thesis/cap2_marco_teorico.md`
8. `thesis/cap4_adquisicion.md`
9. `README.md`
10. `CLAUDE.md`

Flag that `cap4_validacion_offline_legacy.md` and `cap4_adquisicion.md` may create duplicate chapter numbering and should be reviewed before final thesis assembly.
