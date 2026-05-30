# Claude Code phase plan for the radar SAR thesis

Use this plan as the operational roadmap. Each phase must end in a concrete artifact: code, test, figure, metadata schema, report, or thesis section.

## Phase 0 - Repository stabilization

Deliverables:
- Standard folder layout.
- `README.md` with project overview.
- `CLAUDE.md` and `.claude/skills/` installed.
- `.gitignore` protecting raw data and secrets.
- Git checkpoint.

Claude Code prompt:

```text
/radar-repo-audit
```

## Phase 1 - Protect existing working scripts

Deliverables:
- `legacy/` or `experiments/legacy/` folder.
- Inventory of scripts: RX, TX, full-duplex, sweep, OFDM channel estimation.
- No behavior changes yet.

Claude Code prompt:

```text
Create a read-only inventory of existing scripts. Classify each script as RX, TX, full-duplex, sweep, OFDM, plotting, or unknown. Do not edit files.
```

## Phase 2 - Simulation-first SFCW/SAR pipeline

Deliverables:
- Synthetic phantom model.
- Synthetic SFCW data generator.
- Range profile generation.
- Simple 2D reconstruction.
- Unit tests and example figure.

Claude Code prompt:

```text
/radar-simulation-first
```

## Phase 3 - bladeRF device layer

Deliverables:
- `hardware/bladerf_device.py`.
- Read-only hardware info command.
- Config validation.
- No real RF transmission unless confirmed.

Claude Code prompt:

```text
/radar-bladerf-layer legacy_or_script_path.py
```

## Phase 4 - Frequency sweep and OFDM channel estimation

Deliverables:
- `acquisition/sfcw_sweep.py`.
- `acquisition/full_duplex_capture.py`.
- Metadata schema.
- Benchmarks and plots.

Claude Code prompt:

```text
Create or improve the SFCW sweep module using the existing working scripts as reference. Preserve hardware parameters and add a dry-run mode.
```

## Phase 5 - Azimuth stage control

Deliverables:
- `hardware/azimuth_stage.py`.
- Dry-run stage simulator.
- Real serial stage wrapper with homing and limits.
- Safety checklist.

Claude Code prompt:

```text
Implement AzimuthStage with a dry-run simulator first. Include homing, absolute moves, soft limits, settling time, logs, and emergency-stop notes. Do not move real hardware.
```

## Phase 6 - Integrated scan session

Deliverables:
- `acquisition/scan_session.py`.
- Per-position metadata.
- Session manifest.
- Resume/abort behavior.

Claude Code prompt:

```text
Design the scan session orchestration. It must combine stage positions and SFCW sweep calls, but default to dry-run. Real RF/motor actions require explicit approval.
```

## Phase 7 - DSP and stitching pipeline

Deliverables:
- DC offset correction.
- Background subtraction.
- Frequency stitching.
- Phase correction.
- Range profiles.
- Figures and metrics.

Claude Code prompt:

```text
/radar-dsp-pipeline path_to_metadata_or_processed_fixture
```

## Phase 8 - SAR reconstruction and validation

Deliverables:
- Backprojection or delay-and-sum implementation.
- Simulated validation case.
- Phantom result figure.
- Metrics: localization error, contrast, SNR/background ratio, scan time.

Claude Code prompt:

```text
Implement a conservative 2D backprojection reconstruction for near-field SFCW/SAR data. Start from synthetic data and tests before real measurements.
```

## Phase 9 - Thesis writing support

Deliverables:
- Experiment logs.
- Figures with captions.
- Methods text.
- Limitations and future work.

Claude Code prompt:

```text
/radar-thesis-docs reports/session_log.md
```
