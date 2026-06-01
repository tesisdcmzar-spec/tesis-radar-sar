# OFDM Single-Block Capture Plan

## Why This Is the Next Step After f365e39

Commit f365e39 oriented the project to UWB-OFDM-SAR as the primary architecture
and confirmed the simulation pipeline (H(f, x_az) -> range profiles -> backprojection).
The simulation runs end-to-end with synthetic targets.

The next engineering step is to ground the architecture in real hardware: to demonstrate
that one OFDM block of H[k] can be captured from a real bladeRF, using a known
transmitted pilot frame, and to verify that the channel estimation arithmetic
(Y[k] / X[k]) produces a meaningful result.

This document describes the single-block OFDM capture layer added in the session
following f365e39.

## How a Single OFDM Block Estimates H[k]

A known OFDM probing frame is constructed from a deterministic pilot sequence:

    X[k] = BPSK_pilot[k]  for k in active_subcarrier_indices

The time-domain frame (with cyclic prefix) is transmitted by the bladeRF TX channel.
After propagation through the channel and reception on the RX channel:

    Y[k] = H[k] * X[k] + N[k]

where H[k] is the unknown per-subcarrier channel and N[k] is noise.

Since X[k] is known, the channel estimate is:

    H_hat[k] = Y[k] / X[k]

By repeating this over `repetitions` symbols and averaging, noise is reduced:

    H_avg[k] = (1/R) * sum_r H_hat_r[k]

The result is a complex-valued channel transfer function H[k] over the active
subcarriers of one bladeRF instantaneous band (nominally 1-2 MHz for a
conservative first test at 2 MS/s sample rate).

The channel impulse response (CIR) is obtained by windowed IFFT of H[k]:

    h(t) = IFFT{ H[k] * w[k] }

The peak of |h(t)| gives the dominant propagation delay, which corresponds to
a one-way or two-way range.

## What Is Validated by This Step

- OFDM frame generation (build_known_ofdm_frame) produces the correct time-domain
  waveform with cyclic prefix and the correct frequency-domain pilot vector.
- H[k] estimation from a noiseless RX = TX gives H[k] = 1 at all active bins.
- H[k] estimation from a delayed RX produces a CIR peak at the correct delay.
- The capture abstraction (capture_ofdm_block) is testable with a fake device.
- The stitcher scaffold (OFDMBlockStitcher) sorts blocks by frequency, applies
  valid masks, and optionally corrects phase offsets using overlapping bins.
- All tests pass without bladeRF hardware.

In prepare-only mode (default):
- The OFDM frame generation, synthetic RX simulation, and H[k] estimation pipeline
  are validated end-to-end without hardware.

In dry-run mode:
- The capture_ofdm_block function is exercised through the full code path using
  a fake device backend, verifying that no hardware-specific code is accidentally
  invoked in the dry path.

In hardware mode (supervised only):
- One OFDM block is transmitted and received using the real bladeRF.
- Raw IQ data is saved.
- H[k] is estimated and reported.

## What Is NOT Validated by This Step

- Multi-block stitching from real hardware retunes (phase discontinuity at each
  retune is a serious open problem; overlap correction is a scaffold only).
- Calibration of H[k] against a known reflector or through-path.
- Azimuth scanning (motor stage not used in this step).
- SAR image formation (requires calibrated H(f, x_az) cube).
- Dielectric contrast estimation (requires calibrated tissue-phantom H[k]).
- Clinical interpretation (not possible at any stage of this thesis).

## Why Stitching and SAR Are Future Steps

UWB range resolution requires > 500 MHz bandwidth.  One bladeRF block at 2 MS/s
covers only ~1 MHz of active bandwidth.  Covering 500 MHz requires ~500 blocks
at different center frequencies, each retune introducing a random LO phase offset.

Phase stitching without a calibration reference (reflector or cable loop-back) will
produce a discontinuous H(f) that corrupts the CIR and makes backprojection
unreliable.  The stitcher scaffold documents this limitation explicitly.

Azimuth SAR requires repeatable mechanical positioning over many aperture positions,
each requiring a fresh multi-block frequency sweep.  This is addressed only after
a single-block H[k] is validated.

## How This Relates to Dielectric Contrast

In the UWB-OFDM-SAR thesis framework, dielectric-contrast phantoms create reflections
at material boundaries.  The reflection coefficient depends on the complex permittivity
mismatch between materials.  With a calibrated H[k], the complex reflection can be
extracted and related to permittivity via the Fresnel equations or a Born approximation.

This step (single-block H[k]) is a necessary prerequisite: without a verified H[k]
estimation pipeline, no reflection information can be extracted.  The dielectric
interpretation is documented in docs/ofdm_dielectric_interpretation.md.

## Why No Clinical Claims Are Possible

The system is a controlled-lab experimental prototype.  No regulatory approval exists.
No phantom experiments have been performed.  No imaging validation has been done.
No statistical study of detection sensitivity or specificity has been conducted.
Clinical diagnosis of any condition (including cancer) is not possible from this
system at any stage of this thesis.

## Files Added in This Step

- acquisition/ofdm_block_capture.py -- OFDM block capture abstraction
- processing/ofdm_block_stitcher.py -- first block stitching scaffold
- experiments/run_ofdm_single_block_capture.py -- prepare/dry-run/hardware modes
- configs/ofdm_single_block_2p4ghz.yaml -- conservative 2.4 GHz config
- tests/test_ofdm_block_capture.py -- unit tests (fake data, no hardware)
- tests/test_ofdm_block_stitcher.py -- unit tests (synthetic data, no hardware)
- docs/ofdm_single_block_capture_plan.md -- this document
- hardware/bladerf_device.py -- added transmit_iq_burst() for arbitrary OFDM IQ
- hardware/safety.py -- added MAX_OFDM_IQ_BURST_DURATION_S constant

## Recommended Next Step

After validating prepare-only and dry-run:
1. Connect the bladeRF with antennas and a known metal reflector at ~1 m.
2. Run --run-hardware with supervision.
3. Inspect the saved H[k] and CIR for a visible reflection peak.
4. Calibrate using the known reflector distance to verify the delay estimate.
5. If calibration is successful, extend to multiple center-frequency blocks.
6. Implement full multi-block stitching with a reference reflector.
7. Add azimuth scanning and SAR backprojection.
