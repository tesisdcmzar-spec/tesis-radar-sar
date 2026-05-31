"""
Tests for hardware.bladerf_device and hardware.safety.

All tests are hardware-free:
- No bladeRF device is opened.
- No bladeRF Python bindings are imported.
- No RF is transmitted.
- No USB access.
- No motor movement.
"""
from __future__ import annotations

import importlib
import re
import sys
from pathlib import Path

import numpy as np
import pytest

from hardware.safety import (
    BLADERF_MAX_BANDWIDTH_HZ,
    BLADERF_MAX_CAPTURE_SAMPLES,
    BLADERF_MAX_FREQ_HZ,
    BLADERF_MAX_SAMPLE_RATE_HZ,
    BLADERF_MAX_TX_GAIN_DB,
    BLADERF_MIN_FREQ_HZ,
    HardwareConfirmation,
    SafetyError,
    validate_bandwidth_hz,
    validate_frequency_hz,
    validate_gain_db,
    validate_n_samples,
    validate_sample_rate_hz,
)
from hardware.bladerf_device import BladeRFConfig, BladeRFDevice


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

@pytest.fixture
def dry_cfg():
    """A valid dry-run BladeRFConfig at 2.4 GHz."""
    return BladeRFConfig(
        center_freq_hz=2.4e9,
        sample_rate_hz=40e6,
        bandwidth_hz=40e6,
        rx_gain_db=20.0,
        tx_gain_db=-20.0,
        n_samples=1000,
        dry_run=True,
    )


@pytest.fixture
def dry_device(dry_cfg):
    """A fresh BladeRFDevice in dry-run mode."""
    return BladeRFDevice(dry_cfg)


# ---------------------------------------------------------------------------
# BladeRFConfig construction
# ---------------------------------------------------------------------------

def test_dry_run_config_construction(dry_cfg):
    assert dry_cfg.dry_run is True
    assert dry_cfg.center_freq_hz == pytest.approx(2.4e9)
    assert dry_cfg.sample_rate_hz == pytest.approx(40e6)
    assert dry_cfg.n_samples == 1000


def test_default_dry_run_is_true():
    cfg = BladeRFConfig()
    assert cfg.dry_run is True


# ---------------------------------------------------------------------------
# Safety validation — frequency
# ---------------------------------------------------------------------------

def test_frequency_validation_accepts_valid():
    validate_frequency_hz(2.4e9)
    validate_frequency_hz(BLADERF_MIN_FREQ_HZ)
    validate_frequency_hz(BLADERF_MAX_FREQ_HZ)


def test_frequency_validation_rejects_below_minimum():
    with pytest.raises(SafetyError, match="outside the safe operating range"):
        validate_frequency_hz(BLADERF_MIN_FREQ_HZ - 1.0)


def test_frequency_validation_rejects_above_maximum():
    with pytest.raises(SafetyError, match="outside the safe operating range"):
        validate_frequency_hz(BLADERF_MAX_FREQ_HZ + 1.0)


def test_bladerf_config_rejects_out_of_range_frequency():
    with pytest.raises(SafetyError):
        BladeRFConfig(center_freq_hz=10.0)   # 10 Hz is way below 70 MHz


# ---------------------------------------------------------------------------
# Safety validation — bandwidth
# ---------------------------------------------------------------------------

def test_bandwidth_validation_accepts_valid():
    validate_bandwidth_hz(40e6)
    validate_bandwidth_hz(BLADERF_MAX_BANDWIDTH_HZ)


def test_bandwidth_validation_rejects_too_large():
    with pytest.raises(SafetyError, match="outside the safe range"):
        validate_bandwidth_hz(BLADERF_MAX_BANDWIDTH_HZ + 1.0)


def test_bandwidth_validation_rejects_zero():
    with pytest.raises(SafetyError):
        validate_bandwidth_hz(0.0)


# ---------------------------------------------------------------------------
# Safety validation — sample rate
# ---------------------------------------------------------------------------

def test_sample_rate_validation_accepts_valid():
    validate_sample_rate_hz(40e6)
    validate_sample_rate_hz(BLADERF_MAX_SAMPLE_RATE_HZ)


def test_sample_rate_validation_rejects_too_high():
    with pytest.raises(SafetyError, match="outside the safe range"):
        validate_sample_rate_hz(BLADERF_MAX_SAMPLE_RATE_HZ + 1.0)


# ---------------------------------------------------------------------------
# Safety validation — gain
# ---------------------------------------------------------------------------

def test_tx_gain_rejects_above_limit():
    with pytest.raises(SafetyError, match="conservative safety limit"):
        validate_gain_db(BLADERF_MAX_TX_GAIN_DB + 1.0, "tx")


def test_rx_gain_rejects_out_of_range():
    with pytest.raises(SafetyError):
        validate_gain_db(-1.0, "rx")


def test_gain_kind_must_be_tx_or_rx():
    with pytest.raises(ValueError, match="kind must be"):
        validate_gain_db(10.0, "unknown")


# ---------------------------------------------------------------------------
# Safety validation — n_samples
# ---------------------------------------------------------------------------

def test_n_samples_validation_rejects_too_large():
    with pytest.raises(SafetyError, match="outside the safe range"):
        validate_n_samples(BLADERF_MAX_CAPTURE_SAMPLES + 1)


def test_n_samples_validation_rejects_zero():
    with pytest.raises(SafetyError):
        validate_n_samples(0)


# ---------------------------------------------------------------------------
# Real hardware mode safety gate
# ---------------------------------------------------------------------------

def test_real_mode_without_confirmation_raises_safety_error():
    cfg = BladeRFConfig(dry_run=False, center_freq_hz=2.4e9)
    with pytest.raises(SafetyError, match="CONFIRM HARDWARE RUN"):
        BladeRFDevice(cfg, confirmation=None)


def test_real_mode_with_wrong_confirmation_raises_safety_error():
    cfg = BladeRFConfig(dry_run=False, center_freq_hz=2.4e9)
    with pytest.raises(SafetyError, match="CONFIRM HARDWARE RUN"):
        BladeRFDevice(cfg, confirmation="yes please")


def test_hardware_confirmation_phrase():
    """The phrase must be the exact literal string (no typos allowed)."""
    assert HardwareConfirmation.PHRASE == "CONFIRM HARDWARE RUN"


# ---------------------------------------------------------------------------
# Dry-run device lifecycle
# ---------------------------------------------------------------------------

def test_dry_run_device_created(dry_device):
    assert dry_device is not None


def test_configure_rx_sets_flag(dry_device):
    assert not dry_device._configured_rx
    dry_device.configure_rx()
    assert dry_device._configured_rx


def test_configure_tx_sets_flag(dry_device):
    assert not dry_device._configured_tx
    dry_device.configure_tx()
    assert dry_device._configured_tx


def test_capture_rx_without_configure_raises(dry_device):
    with pytest.raises(RuntimeError, match="configure_rx"):
        dry_device.capture_rx()


def test_capture_rx_returns_complex_array(dry_device):
    dry_device.configure_rx()
    iq = dry_device.capture_rx()

    assert isinstance(iq, np.ndarray)
    assert iq.dtype == np.complex128
    assert iq.shape == (dry_device._config.n_samples,)


def test_capture_rx_is_deterministic(dry_cfg):
    """Same config must produce identical IQ arrays."""
    a = BladeRFDevice(dry_cfg)
    a.configure_rx()
    iq_a = a.capture_rx()

    b = BladeRFDevice(dry_cfg)
    b.configure_rx()
    iq_b = b.capture_rx()

    np.testing.assert_array_equal(iq_a, iq_b)


def test_capture_rx_amplitude_is_small(dry_device):
    """Dry-run noise should be well below unit amplitude."""
    dry_device.configure_rx()
    iq = dry_device.capture_rx()
    assert np.mean(np.abs(iq)) < 0.1


# ---------------------------------------------------------------------------
# transmit_tone safety
# ---------------------------------------------------------------------------

def test_transmit_tone_dry_run_does_not_raise(dry_device):
    """In dry-run mode, transmit_tone() must not raise and must not transmit."""
    dry_cfg_local = BladeRFConfig(dry_run=True, n_samples=10)
    dev = BladeRFDevice(dry_cfg_local)
    dev.transmit_tone(freq_offset_hz=1e6, amplitude=0.5)


def test_transmit_tone_dry_run_logs_only(dry_device):
    """Dry-run transmit_tone() must append a log entry, not open hardware."""
    before = len(dry_device._log)
    dry_device.transmit_tone()
    assert len(dry_device._log) > before
    assert "NOT TRANSMITTED" in dry_device._log[-1]


# ---------------------------------------------------------------------------
# Status
# ---------------------------------------------------------------------------

def test_status_returns_dict(dry_device):
    st = dry_device.status()
    assert isinstance(st, dict)
    assert st["dry_run"] is True
    assert "center_freq_hz" in st
    assert "closed" in st


# ---------------------------------------------------------------------------
# Close
# ---------------------------------------------------------------------------

def test_close_marks_device_closed(dry_device):
    assert not dry_device._closed
    dry_device.close()
    assert dry_device._closed


def test_methods_raise_after_close(dry_device):
    dry_device.close()
    with pytest.raises(RuntimeError, match="closed"):
        dry_device.configure_rx()
    with pytest.raises(RuntimeError, match="closed"):
        dry_device.capture_rx()


# ---------------------------------------------------------------------------
# No bladeRF import at module level
# ---------------------------------------------------------------------------

def test_no_bladerf_import_in_bladerf_device_module():
    mod = sys.modules.get("hardware.bladerf_device") or \
          importlib.import_module("hardware.bladerf_device")
    src = Path(mod.__file__).read_text(encoding="utf-8")
    assert not re.search(r"^\s*(import|from)\s+bladerf", src, re.MULTILINE), \
        "hardware.bladerf_device must not import bladeRF at module level"


def test_no_bladerf_import_in_safety_module():
    mod = sys.modules.get("hardware.safety") or \
          importlib.import_module("hardware.safety")
    src = Path(mod.__file__).read_text(encoding="utf-8")
    assert not re.search(r"^\s*(import|from)\s+bladerf", src, re.MULTILINE), \
        "hardware.safety must not import bladeRF"


# ---------------------------------------------------------------------------
# Experiment script helper
# ---------------------------------------------------------------------------

def test_load_bladerf_config_from_yaml():
    """The YAML loader must produce a valid dry-run BladeRFConfig."""
    from experiments.run_bladerf_dry_run import load_bladerf_config_from_yaml

    cfg_path = Path(__file__).resolve().parent.parent / "configs" / "bladerf_dry_run.yaml"
    cfg = load_bladerf_config_from_yaml(cfg_path)

    assert cfg.dry_run is True
    assert cfg.center_freq_hz == pytest.approx(2.4e9)
    assert cfg.n_samples == 40_000
