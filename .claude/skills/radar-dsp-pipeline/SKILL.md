---
name: radar-dsp-pipeline
description: Implement or improve the DSP pipeline for SFCW/OFDM radar data and metadata.
argument-hint: "<metadata-or-fixture-path>"
disable-model-invocation: true
---

Input: $ARGUMENTS

Build the processing pipeline in small tested steps.

Pipeline stages:
1. Load metadata and locate data files without printing raw samples.
2. DC offset correction.
3. Amplitude normalization.
4. Background subtraction.
5. Frequency-block stitching with overlap handling.
6. Phase correction across blocks.
7. IFFT/range profile generation.
8. Save intermediate arrays and figures with reproducible names.
9. Report metrics: frequency range, effective bandwidth, number of positions, range-bin spacing, SNR/background ratio when available.

Rules:
- Do not load huge arrays into the chat context.
- Use scripts to summarize data.
- Keep raw data immutable.
