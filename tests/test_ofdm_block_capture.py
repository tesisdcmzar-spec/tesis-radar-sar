"""
Tests for acquisition/ofdm_block_capture.py.

All tests use synthetic/fake data only. No bladeRF import. No hardware required.
"""
from __future__ import annotations

import numpy as np
import pytest

from acquisition.ofdm_block_capture import (
    OFDMBlockConfig,
    OFDMBlockResult,
    build_known_ofdm_frame,
    capture_ofdm_block,
    estimate_h_from_rx_frame,
    summarize_ofdm_block_result,
    validate_ofdm_block_config,
)
from processing.ofdm_channel import allocate_active_subcarriers


# ---------------------------------------------------------------------------
# Fake device backend (no bladeRF import)
# ---------------------------------------------------------------------------

class FakeDevice:
    """Minimal fake device for testing capture_ofdm_block without hardware."""

    def __init__(self, rx_samples: np.ndarray | None = None):
        self._rx_samples = rx_samples
        self.configure_tx_called = False
        self.configure_rx_called = False
        self.transmit_iq_burst_called = False
        self.last_tx_iq = None

    def configure_tx(self):
        self.configure_tx_called = True

    def configure_rx(self):
        self.configure_rx_called = True

    def transmit_iq_burst(self, iq_samples, **kwargs):
        self.transmit_iq_burst_called = True
        self.last_tx_iq = iq_samples
        return {"dry_run": True, "n_samples_tx": len(iq_samples)}

    def capture_rx(self):
        if self._rx_samples is not None:
            return self._rx_samples
        rng = np.random.default_rng(seed=99)
        n = 8192
        return (rng.standard_normal(n) + 1j * rng.standard_normal(n)) * 0.01

    def close(self):
        pass


# ---------------------------------------------------------------------------
# Default config for most tests
# ---------------------------------------------------------------------------

def make_config(**overrides) -> OFDMBlockConfig:
    defaults = dict(
        center_freq_hz=2.4e9,
        sample_rate_hz=2e6,
        bandwidth_hz=2e6,
        n_fft=64,
        n_active=32,
        cp_len=16,
        guard_bins=4,
        dc_null=True,
        pilot_type="bpsk",
        pilot_seed=42,
        repetitions=4,
        tx_gain_db=-20.0,
        rx_gain_db=20.0,
    )
    defaults.update(overrides)
    return OFDMBlockConfig(**defaults)


# ---------------------------------------------------------------------------
# validate_ofdm_block_config
# ---------------------------------------------------------------------------

class TestValidateOFDMBlockConfig:
    def test_valid_config_passes(self):
        cfg = make_config()
        validate_ofdm_block_config(cfg)  # should not raise

    def test_n_fft_too_small(self):
        cfg = make_config(n_fft=8)
        with pytest.raises(ValueError, match="n_fft"):
            validate_ofdm_block_config(cfg)

    def test_n_active_too_large(self):
        cfg = make_config(n_fft=64, n_active=128)
        with pytest.raises(ValueError, match="n_active"):
            validate_ofdm_block_config(cfg)

    def test_negative_cp_len(self):
        cfg = make_config(cp_len=-1)
        with pytest.raises(ValueError, match="cp_len"):
            validate_ofdm_block_config(cfg)

    def test_negative_guard_bins(self):
        cfg = make_config(guard_bins=-1)
        with pytest.raises(ValueError, match="guard_bins"):
            validate_ofdm_block_config(cfg)

    def test_invalid_pilot_type(self):
        cfg = make_config(pilot_type="psk8")
        with pytest.raises(ValueError, match="pilot_type"):
            validate_ofdm_block_config(cfg)

    def test_zero_repetitions(self):
        cfg = make_config(repetitions=0)
        with pytest.raises(ValueError, match="repetitions"):
            validate_ofdm_block_config(cfg)

    def test_human_subject_rejected(self):
        cfg = make_config(human_subject=True)
        with pytest.raises(ValueError, match="human_subject"):
            validate_ofdm_block_config(cfg)

    def test_phantom_rejected(self):
        cfg = make_config(phantom=True)
        with pytest.raises(ValueError, match="phantom"):
            validate_ofdm_block_config(cfg)

    def test_motor_scan_rejected(self):
        cfg = make_config(motor_scan=True)
        with pytest.raises(ValueError, match="motor_scan"):
            validate_ofdm_block_config(cfg)

    def test_sar_scan_rejected(self):
        cfg = make_config(sar_scan=True)
        with pytest.raises(ValueError, match="sar_scan"):
            validate_ofdm_block_config(cfg)

    def test_qpsk_pilot_valid(self):
        cfg = make_config(pilot_type="qpsk")
        validate_ofdm_block_config(cfg)  # should not raise


# ---------------------------------------------------------------------------
# build_known_ofdm_frame
# ---------------------------------------------------------------------------

class TestBuildKnownOFDMFrame:
    def test_output_shapes(self):
        cfg = make_config(n_fft=64, n_active=32, cp_len=16, repetitions=4)
        tx_time, tx_freq = build_known_ofdm_frame(cfg)
        sym_len = cfg.cp_len + cfg.n_fft
        assert tx_time.shape == (4 * sym_len,), f"tx_time shape {tx_time.shape}"
        assert tx_freq.shape == (cfg.n_fft,), f"tx_freq shape {tx_freq.shape}"

    def test_tx_freq_has_zero_dc(self):
        cfg = make_config(dc_null=True)
        _, tx_freq = build_known_ofdm_frame(cfg)
        assert tx_freq[0] == 0.0 + 0.0j

    def test_tx_freq_bpsk_magnitudes(self):
        cfg = make_config(pilot_type="bpsk")
        active_idx = allocate_active_subcarriers(
            cfg.n_fft, cfg.n_active, dc_null=cfg.dc_null, guard_bins=cfg.guard_bins
        )
        _, tx_freq = build_known_ofdm_frame(cfg)
        active_mags = np.abs(tx_freq[active_idx])
        assert np.allclose(active_mags, 1.0), "BPSK pilots must have unit magnitude"

    def test_tx_freq_qpsk_magnitudes(self):
        cfg = make_config(pilot_type="qpsk")
        active_idx = allocate_active_subcarriers(
            cfg.n_fft, cfg.n_active, dc_null=cfg.dc_null, guard_bins=cfg.guard_bins
        )
        _, tx_freq = build_known_ofdm_frame(cfg)
        active_mags = np.abs(tx_freq[active_idx])
        assert np.allclose(active_mags, 1.0), "QPSK pilots must have unit magnitude"

    def test_inactive_bins_zero(self):
        cfg = make_config(dc_null=True)
        active_idx = allocate_active_subcarriers(
            cfg.n_fft, cfg.n_active, dc_null=cfg.dc_null, guard_bins=cfg.guard_bins
        )
        _, tx_freq = build_known_ofdm_frame(cfg)
        inactive_mask = np.ones(cfg.n_fft, dtype=bool)
        inactive_mask[active_idx] = False
        assert np.all(tx_freq[inactive_mask] == 0.0), "Inactive bins must be zero"

    def test_deterministic_with_seed(self):
        cfg = make_config(pilot_seed=99)
        _, tx_freq_a = build_known_ofdm_frame(cfg)
        _, tx_freq_b = build_known_ofdm_frame(cfg)
        assert np.allclose(tx_freq_a, tx_freq_b), "Must be deterministic with same seed"

    def test_different_seeds_differ(self):
        cfg_a = make_config(pilot_seed=1)
        cfg_b = make_config(pilot_seed=2)
        _, tx_freq_a = build_known_ofdm_frame(cfg_a)
        _, tx_freq_b = build_known_ofdm_frame(cfg_b)
        assert not np.allclose(tx_freq_a, tx_freq_b), "Different seeds should produce different pilots"


# ---------------------------------------------------------------------------
# estimate_h_from_rx_frame
# ---------------------------------------------------------------------------

class TestEstimateHFromRXFrame:
    def test_noiseless_h_equals_1_at_active_bins(self):
        cfg = make_config(n_fft=64, n_active=32, cp_len=16, repetitions=2)
        tx_time, tx_freq = build_known_ofdm_frame(cfg)

        # Noiseless: RX = TX (identity channel)
        H = estimate_h_from_rx_frame(tx_time, tx_freq, cfg)

        active_idx = allocate_active_subcarriers(
            cfg.n_fft, cfg.n_active, dc_null=cfg.dc_null, guard_bins=cfg.guard_bins
        )
        H_active = H[active_idx]
        assert np.allclose(np.abs(H_active), 1.0, atol=1e-6), \
            f"H magnitude at active bins should be 1.0 for identity channel; got {np.abs(H_active)}"

    def test_h_is_zero_at_inactive_bins(self):
        cfg = make_config(n_fft=64, n_active=32, cp_len=16, repetitions=2)
        tx_time, tx_freq = build_known_ofdm_frame(cfg)
        H = estimate_h_from_rx_frame(tx_time, tx_freq, cfg)

        active_idx = allocate_active_subcarriers(
            cfg.n_fft, cfg.n_active, dc_null=cfg.dc_null, guard_bins=cfg.guard_bins
        )
        inactive_mask = np.ones(cfg.n_fft, dtype=bool)
        inactive_mask[active_idx] = False
        # Inactive bins should be zero (no TX pilot -> H[k]=0 by convention)
        assert np.allclose(np.abs(H[inactive_mask]), 0.0, atol=1e-10)

    def test_single_path_delay_recoverable(self):
        """H[k] from a delayed version of tx_time should encode the delay."""
        cfg = make_config(n_fft=64, n_active=32, cp_len=16, repetitions=1)
        tx_time, tx_freq = build_known_ofdm_frame(cfg)
        delay_samples = 5
        rx_iq = np.zeros_like(tx_time)
        rx_iq[delay_samples:] = tx_time[: len(tx_time) - delay_samples]

        H = estimate_h_from_rx_frame(rx_iq, tx_freq, cfg)

        from processing.ofdm_channel import channel_impulse_response
        cir = channel_impulse_response(H)
        peak_idx = int(np.argmax(np.abs(cir)))
        # Allow +/-2 sample tolerance
        assert abs(peak_idx - delay_samples) <= 2, \
            f"CIR peak at {peak_idx}, expected ~{delay_samples}"

    def test_short_rx_does_not_crash(self):
        cfg = make_config(n_fft=32, n_active=16, cp_len=8, repetitions=3)
        tx_time, tx_freq = build_known_ofdm_frame(cfg)
        short_rx = tx_time[: len(tx_time) // 2]  # truncated
        # Should not raise; result may be averaged over fewer symbols
        H = estimate_h_from_rx_frame(short_rx, tx_freq, cfg)
        assert H.shape == (cfg.n_fft,)


# ---------------------------------------------------------------------------
# capture_ofdm_block (dry-run, fake device)
# ---------------------------------------------------------------------------

class TestCaptureOFDMBlock:
    def test_dry_run_returns_result(self):
        cfg = make_config(n_fft=64, n_active=32, cp_len=16, repetitions=4)
        device = FakeDevice()
        result = capture_ofdm_block(device, cfg, dry_run=True)
        assert isinstance(result, OFDMBlockResult)
        assert result.dry_run is True

    def test_dry_run_h_shape(self):
        cfg = make_config(n_fft=64, n_active=32, cp_len=16, repetitions=4)
        result = capture_ofdm_block(FakeDevice(), cfg, dry_run=True)
        assert result.H.shape == (cfg.n_fft,)

    def test_dry_run_h_active_bins_nonzero(self):
        cfg = make_config(n_fft=64, n_active=32, cp_len=16, repetitions=4)
        result = capture_ofdm_block(FakeDevice(), cfg, dry_run=True)
        assert np.any(np.abs(result.H_active) > 0)

    def test_dry_run_active_indices_shape(self):
        cfg = make_config(n_fft=64, n_active=32, cp_len=16, guard_bins=2)
        result = capture_ofdm_block(FakeDevice(), cfg, dry_run=True)
        expected_active = allocate_active_subcarriers(
            cfg.n_fft, cfg.n_active, dc_null=cfg.dc_null, guard_bins=cfg.guard_bins
        )
        assert result.active_indices.shape == expected_active.shape

    def test_dry_run_freqs_hz_length_matches_active(self):
        cfg = make_config(n_fft=64, n_active=32, cp_len=16)
        result = capture_ofdm_block(FakeDevice(), cfg, dry_run=True)
        assert len(result.freqs_hz) == len(result.active_indices)

    def test_dry_run_freqs_hz_near_center(self):
        cfg = make_config(center_freq_hz=2.4e9, n_fft=64, n_active=32, cp_len=16)
        result = capture_ofdm_block(FakeDevice(), cfg, dry_run=True)
        freq_center = float(np.mean(result.freqs_hz))
        # Center of active band should be close to the RF center freq
        assert abs(freq_center - cfg.center_freq_hz) < cfg.sample_rate_hz

    def test_dry_run_with_perfect_channel_h_magnitude_near_1(self):
        """In dry_run, RX = TX + tiny noise; H active should be ~1."""
        cfg = make_config(n_fft=64, n_active=32, cp_len=16, repetitions=8)
        result = capture_ofdm_block(FakeDevice(), cfg, dry_run=True)
        mag = np.abs(result.H_active)
        assert float(np.mean(mag)) > 0.9, f"Mean |H| should be near 1.0, got {np.mean(mag):.4f}"

    def test_no_bladerf_import_in_dry_run(self):
        import sys
        before = set(sys.modules.keys())
        cfg = make_config()
        capture_ofdm_block(FakeDevice(), cfg, dry_run=True)
        new_modules = set(sys.modules.keys()) - before
        bladerf_mods = [m for m in new_modules if "bladerf" in m.lower()]
        assert not bladerf_mods, f"bladeRF was imported during dry_run: {bladerf_mods}"

    def test_real_mode_requires_confirmation(self):
        from hardware.safety import SafetyError
        cfg = make_config()
        device = FakeDevice()
        with pytest.raises(SafetyError):
            capture_ofdm_block(device, cfg, dry_run=False, confirmation=None)

    def test_fake_device_real_mode_with_confirmation(self):
        cfg = make_config(n_fft=64, n_active=32, cp_len=16, repetitions=2)
        sym_len = cfg.cp_len + cfg.n_fft
        n_rx = sym_len * cfg.repetitions
        tx_time, _ = build_known_ofdm_frame(cfg)
        rx_samples = tx_time + np.random.default_rng(0).standard_normal(n_rx) * 0.01
        device = FakeDevice(rx_samples=rx_samples)
        result = capture_ofdm_block(
            device, cfg,
            dry_run=False,
            confirmation="CONFIRM HARDWARE RUN",
            reflector_setup_ready="REFLECTOR SETUP READY",
        )
        assert device.configure_tx_called
        assert device.configure_rx_called
        assert device.transmit_iq_burst_called
        assert result.dry_run is False
        assert result.H.shape == (cfg.n_fft,)


# ---------------------------------------------------------------------------
# summarize_ofdm_block_result
# ---------------------------------------------------------------------------

class TestSummarizeOFDMBlockResult:
    def test_summary_is_string(self):
        cfg = make_config()
        result = capture_ofdm_block(FakeDevice(), cfg, dry_run=True)
        summary = summarize_ofdm_block_result(result)
        assert isinstance(summary, str)
        assert len(summary) > 50

    def test_summary_ascii_only(self):
        cfg = make_config()
        result = capture_ofdm_block(FakeDevice(), cfg, dry_run=True)
        summary = summarize_ofdm_block_result(result)
        summary.encode("ascii")  # should not raise

    def test_summary_contains_key_fields(self):
        cfg = make_config(center_freq_hz=2.4e9)
        result = capture_ofdm_block(FakeDevice(), cfg, dry_run=True)
        summary = summarize_ofdm_block_result(result)
        assert "2400" in summary or "2.4" in summary
        assert "dry_run" in summary.lower()
