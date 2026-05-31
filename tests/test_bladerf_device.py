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
import unittest.mock
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
from hardware.bladerf_device import BladeRFConfig, BladeRFDevice, _import_bladerf, sc16q11_to_complex


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


# ---------------------------------------------------------------------------
# sc16q11_to_complex — conversion helper
# ---------------------------------------------------------------------------

def test_sc16q11_zeros_returns_zero_complex():
    raw = np.zeros(8, dtype=np.int16)
    out = sc16q11_to_complex(raw)
    assert np.all(out == 0 + 0j)


def test_sc16q11_output_dtype_is_complex128():
    raw = np.zeros(4, dtype=np.int16)
    assert sc16q11_to_complex(raw).dtype == np.complex128


def test_sc16q11_output_shape_is_half_input():
    raw = np.zeros(100, dtype=np.int16)
    assert sc16q11_to_complex(raw).shape == (50,)


def test_sc16q11_known_interleaved_values():
    # [I0=2048, Q0=0, I1=0, Q1=2048] → [1+0j, 0+1j]
    raw = np.array([2048, 0, 0, 2048], dtype=np.int16)
    out = sc16q11_to_complex(raw)
    np.testing.assert_allclose(out, [1.0 + 0j, 0.0 + 1j], atol=1e-9)


def test_sc16q11_normalization_divides_by_2048():
    # Max positive SC16_Q11 value = 2047 on both I and Q
    raw = np.array([2047, 2047], dtype=np.int16)
    out = sc16q11_to_complex(raw)
    assert out[0].real == pytest.approx(2047 / 2048.0)
    assert out[0].imag == pytest.approx(2047 / 2048.0)


def test_sc16q11_negative_values():
    raw = np.array([-2048, -2048], dtype=np.int16)
    out = sc16q11_to_complex(raw)
    assert out[0].real == pytest.approx(-1.0)
    assert out[0].imag == pytest.approx(-1.0)


def test_sc16q11_odd_length_raises_value_error():
    raw = np.array([1, 2, 3], dtype=np.int16)
    with pytest.raises(ValueError, match="even length"):
        sc16q11_to_complex(raw)


def test_sc16q11_2d_array_raises_value_error():
    raw = np.zeros((2, 4), dtype=np.int16)
    with pytest.raises(ValueError, match="even length"):
        sc16q11_to_complex(raw)


# ---------------------------------------------------------------------------
# _import_bladerf — lazy import helper
# ---------------------------------------------------------------------------

def test_import_bladerf_raises_when_not_installed():
    """_import_bladerf() must raise ImportError when the package is absent."""
    with unittest.mock.patch.dict(sys.modules, {"bladerf": None}):
        with pytest.raises(ImportError, match="bladeRF Python bindings"):
            _import_bladerf()


# ---------------------------------------------------------------------------
# Fake bladeRF backend — for real-mode path tests without USB
# ---------------------------------------------------------------------------

class _FakeChannel:
    """Minimal fake bladeRF channel object."""
    frequency: int = 0
    sample_rate: int = 0
    bandwidth: int = 0
    gain: int = 0


class _FakeBladeRFDevice:
    """Fake bladeRF device returned by _FakeBladeRFModule.BladeRF()."""

    def __init__(self) -> None:
        self._ch = _FakeChannel()
        self.sync_configured: bool = False
        self.rx_calls: int = 0
        self.closed: bool = False

    def Channel(self, ch_id):
        return self._ch

    def sync_config(self, **kwargs) -> None:
        self.sync_configured = True

    def sync_rx(self, buf: bytearray, n_samples: int) -> None:
        buf[:n_samples * 4] = bytes(n_samples * 4)
        self.rx_calls += 1

    def enable_module(self, ch_id, enable: bool) -> None:
        pass

    def close(self) -> None:
        self.closed = True


class _FakeBladeRFSubmodule:
    """Mimics bladerf._bladerf which hosts ChannelLayout and Format."""

    class ChannelLayout:
        RX_X1 = "RX_X1"

    class Format:
        SC16_Q11 = "SC16_Q11"


class _FakeBladeRFModule:
    """Fake bladeRF module injectable via BladeRFDevice(_bladerf_module=...)."""

    def __init__(self) -> None:
        self._last_device: "_FakeBladeRFDevice | None" = None
        # Mimic bladerf._bladerf submodule (hosts ChannelLayout and Format).
        self._bladerf = _FakeBladeRFSubmodule()

    def BladeRF(self) -> _FakeBladeRFDevice:
        self._last_device = _FakeBladeRFDevice()
        return self._last_device

    @staticmethod
    def CHANNEL_RX(n: int) -> int:
        return n


# ---------------------------------------------------------------------------
# Real-mode path with fake backend (no USB, no RF)
# ---------------------------------------------------------------------------

@pytest.fixture
def fake_mod():
    return _FakeBladeRFModule()


@pytest.fixture
def real_cfg():
    return BladeRFConfig(
        center_freq_hz=2.4e9,
        sample_rate_hz=40e6,
        bandwidth_hz=40e6,
        rx_gain_db=20.0,
        tx_gain_db=-20.0,
        n_samples=1000,
        dry_run=False,
    )


def test_real_mode_with_fake_backend_constructs(real_cfg, fake_mod):
    dev = BladeRFDevice(real_cfg, confirmation="CONFIRM HARDWARE RUN",
                        _bladerf_module=fake_mod)
    assert dev is not None
    assert fake_mod._last_device is not None


def test_real_mode_with_fake_backend_opens_device(real_cfg, fake_mod):
    BladeRFDevice(real_cfg, confirmation="CONFIRM HARDWARE RUN",
                  _bladerf_module=fake_mod)
    assert isinstance(fake_mod._last_device, _FakeBladeRFDevice)


def test_real_mode_with_fake_backend_configure_rx_sets_channel(real_cfg, fake_mod):
    dev = BladeRFDevice(real_cfg, confirmation="CONFIRM HARDWARE RUN",
                        _bladerf_module=fake_mod)
    dev.configure_rx()
    ch = fake_mod._last_device._ch
    assert ch.frequency == int(2.4e9)
    assert ch.sample_rate == int(40e6)
    assert ch.bandwidth == int(40e6)
    assert ch.gain == 20


def test_real_mode_with_fake_backend_capture_rx_returns_complex_array(real_cfg, fake_mod):
    dev = BladeRFDevice(real_cfg, confirmation="CONFIRM HARDWARE RUN",
                        _bladerf_module=fake_mod)
    dev.configure_rx()
    iq = dev.capture_rx()
    assert isinstance(iq, np.ndarray)
    assert iq.dtype == np.complex128
    assert iq.shape == (1000,)


def test_real_mode_with_fake_backend_capture_calls_sync_rx(real_cfg, fake_mod):
    dev = BladeRFDevice(real_cfg, confirmation="CONFIRM HARDWARE RUN",
                        _bladerf_module=fake_mod)
    dev.configure_rx()
    dev.capture_rx()
    assert fake_mod._last_device.rx_calls == 1


def test_real_mode_with_fake_backend_capture_configures_sync(real_cfg, fake_mod):
    dev = BladeRFDevice(real_cfg, confirmation="CONFIRM HARDWARE RUN",
                        _bladerf_module=fake_mod)
    dev.configure_rx()
    dev.capture_rx()
    assert fake_mod._last_device.sync_configured is True


def test_real_mode_with_fake_backend_close_calls_device_close(real_cfg, fake_mod):
    dev = BladeRFDevice(real_cfg, confirmation="CONFIRM HARDWARE RUN",
                        _bladerf_module=fake_mod)
    dev.close()
    assert fake_mod._last_device.closed is True
    assert dev._closed is True


def test_real_mode_with_fake_backend_zero_buffer_gives_zero_iq(real_cfg, fake_mod):
    """Fake sync_rx fills zeros → IQ should be all zero after SC16_Q11 conversion."""
    dev = BladeRFDevice(real_cfg, confirmation="CONFIRM HARDWARE RUN",
                        _bladerf_module=fake_mod)
    dev.configure_rx()
    iq = dev.capture_rx()
    assert np.all(iq == 0 + 0j)
