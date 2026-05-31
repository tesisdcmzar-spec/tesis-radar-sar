---
name: radar-auto
description: Safe workflow router for the Radar SAR thesis. Use when the user does not know what to do next, wants automatic selection between /radar-* skills, wants to start or close a session, audit the repo, continue an offline phase, document work, prepare thesis text, publish reports, or detect whether a task touches hardware. Classifies the task, inspects repo state with read-only commands, and returns the exact next prompt or workflow. Never transmits RF or moves motors.
disable-model-invocation: true
---

# `/radar-auto` — Safe Workflow Router for Radar SAR Thesis

## Purpose

Act as an operational dispatcher. The skill must inspect the project state, classify the user's intent, and recommend the exact next step.

This is not a "do everything blindly" skill. It should reduce decision fatigue for the user while preserving safety, traceability, and thesis-quality documentation.

## Allowed inspection commands

The skill may run only read-only or safe validation commands:

```powershell
git status
git log --oneline -10
git diff --stat
dir .claude\skills
dir reports\session_reports
dir thesis
dir acquisition
dir processing
dir simulation
```

It may also read these files if they exist:

```text
CLAUDE.md
README.md
reports/ai_session_log.md
reports/session_reports/*.md
configs/simulation.yaml
```

For `.npy` inspection, only allow:

```python
np.load(path, mmap_mode="r")
```

and report only:

* filename
* shape
* dtype
* estimated size
* inferred frequency if encoded in the filename

## Task classification

Classify the user's request into exactly one of these categories:

1. `session_start`

   * The user is starting a new work session.
   * Recommend `/radar-session-start` if it exists.
   * If it does not exist, recommend a manual safe startup checklist.

2. `repo_audit`

   * The user is lost or wants to know the general repo state.
   * Recommend `/radar-repo-audit` if it exists.
   * If it does not exist, propose safe read-only inspection commands.

3. `offline_phase_work`

   * Work without hardware: loaders, `.npy` analysis, simulation, offline tests, figure generation, reports.
   * May recommend a direct prompt.
   * May recommend continuing or closing Phase 2 offline if appropriate.

4. `simulation_work`

   * Changes in `simulation/`, `processing/`, `experiments/run_simulation.py`, or simulated figures.
   * Recommend `/radar-simulation-first` only for large simulation tasks.
   * For small changes, recommend a direct prompt.

5. `real_data_loader`

   * Loading `.npy`, adapting real or legacy data to `SyntheticScan`, inspecting `legacy/capturas_barrido/`.
   * Recommend a safe direct prompt.
   * Hardware is forbidden.

6. `hardware_layer`

   * Creating a bladeRF wrapper, dry-run layer, safe TX/RX abstraction.
   * Recommend creating/using a hardware skill only in dry-run mode.
   * If real RF is required, demand `CONFIRM HARDWARE RUN`.

7. `rf_or_motor_run`

   * Any task involving TX, real RX with active TX, RF sweep, motor movement, firmware, or drivers.
   * Stop.
   * Explain that the user must be present.
   * Require the exact phrase `CONFIRM HARDWARE RUN`.
   * Do not execute anything.

8. `thesis_documentation`

   * Thesis chapters in `thesis/`, academic writing, theory, simulation, validation.
   * Recommend a direct prompt or `/radar-thesis-docs` if it exists.

9. `session_close`

   * The user wants to close a session, generate a report, commit, or preserve traceability.
   * Recommend `/radar-session-close`.

10. `notion_or_publish`

    * The user wants to publish reports to Notion or sync reports.
    * Recommend a publishing workflow, but do not publish automatically unless a script and environment variables are already configured.

11. `small_direct_task`

    * A precise task that does not need a skill.
    * Provide a short exact prompt.

12. `ambiguous`

    * Missing information.
    * Ask exactly one clarification question.

## Decision rules

* If hardware is physically connected but the task can be done offline, treat it as offline and forbid RF.
* If there are uncommitted changes and the user wants to start another phase, recommend documenting/closing first.
* If new reports exist but `ai_session_log.md` was not updated, recommend traceability update.
* If new code exists without tests, recommend tests before reports.
* If tests are failing, do not recommend commit or push.
* If the task targets final thesis text, separate:

  * session report = engineering log / technical traceability
  * thesis chapter = academic writing
* Do not recommend "do everything" if the task mixes hardware, thesis writing, and acquisition. Split by phases.

## Required output format

The skill must always respond with this structure:

```markdown
# Diagnosis

Brief repo/task state.

# Classification

Detected category: `<category>`

# Recommended skill or workflow

State:
- recommended skill, if applicable
- or direct prompt, if no skill is needed

# Why

Short explanation.

# Files likely to be touched

Short list.

# Safe commands allowed

Short list.

# Commands forbidden in this task

Short list.

# Exact next prompt to paste

A copy-ready prompt block.
```

## Autonomous offline mode

If the user explicitly asks for autonomous work and the task is classified as `offline_phase_work`, `real_data_loader`, `simulation_work`, or `thesis_documentation`, the skill may propose an autonomous prompt that includes:

* repo inspection
* tests
* report creation
* `reports/ai_session_log.md` update
* commit
* push

But only if:

* no hardware is involved;
* no RF is involved;
* no motors are involved;
* no firmware is involved;
* no huge data files need to be loaded fully into memory.

## Hardware mode

If the task involves real hardware, the output must say:

```text
This task requires real hardware. It must not run autonomously.
To continue, the user must be present and type:
CONFIRM HARDWARE RUN
```

Do not execute any hardware command.

## Classification examples

### Example 1

User:
"I want to close the offline phase and generate a report."

Classification:
`offline_phase_work`

Recommendation:
Autonomous offline prompt with tests, analysis, report, commit, and push.

### Example 2

User:
"I want to run a sweep with TX1 and RX1 now."

Classification:
`rf_or_motor_run`

Recommendation:
Stop and require `CONFIRM HARDWARE RUN`.

### Example 3

User:
"I do not know what is missing in the repo."

Classification:
`repo_audit`

Recommendation:
`/radar-repo-audit` or safe inspection commands.

### Example 4

User:
"Turn this report into a thesis chapter."

Classification:
`thesis_documentation`

Recommendation:
Direct prompt or `/radar-thesis-docs`.
