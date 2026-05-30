# Prompt library for Claude Code

Use these prompts in English inside Claude Code. Replace paths as needed.

## Read-only repository overview

```text
Read-only task. Inspect the repository structure, README, CLAUDE.md, configs, and tests. Do not edit files. Return a concise map of modules, scripts, missing pieces, and the safest next step.
```

## Protect a working script before refactor

```text
This script works on Windows with bladeRF. Treat it as fragile. First explain what it does by block. Then propose a minimal refactor plan that preserves behavior and hardware parameters. Do not edit yet: <path>
```

## Minimal refactor

```text
Apply the approved minimal refactor to <path>. Preserve all RF parameters, buffer sizes, timing assumptions, metadata fields, and output formats. Add small functions only. Run tests if available. Show the diff summary.
```

## Bug from traceback

```text
Fix this error with the smallest possible change. Do not change hardware parameters or acquisition logic unless the traceback proves they are the cause. Error:

<paste traceback>
```

## Dataset summary without loading huge arrays into context

```text
Create a Python script that summarizes this dataset without printing raw samples. It should report filenames, array shape, dtype, metadata keys, frequency range, azimuth positions, and basic amplitude statistics. Do not ask to read raw .npy files directly.
```

## Simulation task

```text
Create a simulation-first SFCW/SAR pipeline: synthetic phantom, synthetic frequency response, range profile with IFFT, and simple 2D reconstruction. Keep it testable and independent from real hardware.
```

## Processing task

```text
Implement the processing pipeline for complex I/Q SFCW data: load metadata, remove DC offset, normalize, subtract background, stitch frequency blocks, correct phase discontinuities, compute range profiles, and save intermediate figures.
```

## Thesis documentation task

```text
Using the latest experiment logs and figures, draft a thesis-ready technical section in Spanish. Keep claims limited to simulation/phantom validation. Do not claim clinical diagnosis.
```

## End session summary

```text
Summarize this session into reports/ai_session_log.md with: date, goal, files changed, commands run, tests/results, unresolved issues, next step, and hardware risk notes.
```
