---
name: radar-scan-session
description: Design the integrated scan session that combines azimuth motion, SFCW sweep, metadata, logs, and safety.
disable-model-invocation: true
---

Design or improve scan orchestration.

Required behavior:
1. Default dry-run mode.
2. Explicit config file for frequencies, bandwidth, gains, positions, dwell/settling time, output folder, and safety limits.
3. Session manifest with timestamp, git commit hash if available, config copy, operator notes, and hardware state.
4. For each azimuth position: move/dry-run, settle, sweep/dry-run, save data, save metadata, validate capture, continue.
5. Abort/resume design.
6. Clear separation between stage control, bladeRF capture, and orchestration.

Never run real motion or RF transmission without explicit user approval in the current session.
