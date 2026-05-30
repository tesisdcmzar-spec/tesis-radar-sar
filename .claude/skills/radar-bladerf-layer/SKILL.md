---
name: radar-bladerf-layer
description: Design or refactor the Python bladeRF abstraction layer while protecting working acquisition scripts.
argument-hint: "<reference-script-or-folder>"
disable-model-invocation: true
---

Reference: $ARGUMENTS

Goal: create or improve `hardware/bladerf_device.py` without breaking working scripts.

Requirements:
1. Preserve known-good hardware parameters from reference scripts.
2. Support configuration of frequency, sample rate, bandwidth, gains, TX/RX, and full-duplex capture.
3. Add dry-run/mock mode for tests.
4. Centralize metadata generation.
5. Validate parameter ranges before hardware calls.
6. Log configuration and errors.
7. Do not run real bladeRF commands unless the user explicitly approves in the current session.

Output a short implementation plan before editing.
