"""
Safe bladeRF hardware abstraction layer.

Design principles
-----------------
1. dry_run=True is the default.  In dry-run mode, no USB device is opened,
   no RF is transmitted, and no real bladeRF API is imported.

2. Real hardware mode (dry_run=False) requires the exact confirmation string
   'CONFIRM HARDWARE RUN' to be passed to __init__().  Without it, SafetyError
   is raised before any hardware operation begins.  The confirmation is not
   persistent between sessions.

3. bladeRF Python bindings are never imported at module load time.  They are
   obtained via _import_bladerf(), which uses importlib.import_module() only
   when dry_run=False AND confirmation has been validated.  This ensures tests
   and offline scripts never trigger USB access by accident.

4. transmit_tone() always raises SafetyError when dry_run=False (TX not yet
   implemented).  In dry-run mode it simulates logging without emitting RF.

5. sc16q11_to_complex() is a standalone helper that converts the bladeRF
   SC16_Q11 wire format (interleaved int16) to complex128.  It is
   independently testable without any hardware.

Current status
--------------
The real RX capture path (configure_rx + capture_rx via _capture_rx_real) is
implemented using the libbladeRF Python bindings API structure.  It has NOT
been executed on real hardware.  First real hardware execution requires:
  - User presence
  - bladeRF device physically connected
  - Exact confirmation string: 'CONFIRM HARDWARE RUN' passed at construction
"""
from __future__ import annotations

import importlib
from dataclasses import dataclass, field

import numpy as np

from hardware.safety import (
    HardwareConfirmation,
    SafetyError,
    require_hardware_confirmation,
    validate_bandwidth_hz,
    validate_frequency_hz,
    validate_gain_db,
    validate_n_samples,
    validate_sample_rate_hz,
)


# ---------------------------------------------------------------------------
# SC16_Q11 sample conversion
# ---------------------------------------------------------------------------

def sc16q11_to_complex(raw: np.ndarray) -> np.ndarray:
    """
    Convert SC16_Q11 interleaved int16 buffer to complex128 IQ samples.

    The bladeRF SC16_Q11 format stores each sample as a pair of signed 16-bit
    integers [I, Q].  The wire layout is [I0, Q0, I1, Q1, ...].  Values span
    [-2048, +2047] (Q1.11 fixed-point); dividing by 2048.0 normalises to
    approximately [-1, +1).

    Parameters
    ----------
    raw : np.ndarray
        1-D array of interleaved I/Q samples: [I0, Q0, I1, Q1, ...].
        Must have even length (2 x n_samples).  Interpreted as int16.

    Returns
    -------
    np.ndarray
        Complex128 array of shape (len(raw) // 2,).

    Raises
    ------
    ValueError
        If raw is not 1-D or has odd length.
    """
    if raw.ndim != 1 or raw.size % 2 != 0:
        raise ValueError(
            f"raw must be a 1-D array with even length; got shape={raw.shape}"
        )
    raw_i16 = raw.astype(np.int16, copy=False)
    i_ch = raw_i16[0::2].astype(np.float64)
    q_ch = raw_i16[1::2].astype(np.float64)
    return (i_ch + 1j * q_ch) / 2048.0


# ---------------------------------------------------------------------------
# Lazy bladeRF import
# ---------------------------------------------------------------------------

def _import_bladerf():
    """
    Lazy import of the bladeRF Python bindings via importlib.

    Called only inside BladeRFDevice methods when dry_run=False and the
    confirmation phrase has already been validated.  Never called at module
    load time — the word 'bladerf' never appears in a top-level import
    statement in this file.

    Returns
    -------
    module
        The imported ``bladerf`` module.

    Raises
    ------
    ImportError
        If the bladeRF Python package is not installed.
    """
    try:
        return importlib.import_module("bladerf")
    except ImportError as exc:
        raise ImportError(
            "bladeRF Python bindings not found.  "
            "Install with: pip install bladerf\n"
            "Or build from source: https://github.com/Nuand/bladeRF"
        ) from exc


# ---------------------------------------------------------------------------
# Configuration
# ---------------------------------------------------------------------------

@dataclass
class BladeRFConfig:
    """
    Validated configuration for a single bladeRF capture session.

    All parameters are validated against safe limits on construction.
    Parameters are also validated again inside BladeRFDevice.__init__() to
    catch any post-construction mutations.
    """

    center_freq_hz: float = 2.4e9       # RX center frequency [Hz]
    sample_rate_hz: float = 40.0e6      # ADC/DAC sample rate [samples/s]
    bandwidth_hz: float = 40.0e6        # analog low-pass bandwidth [Hz]
    rx_gain_db: float = 20.0            # RX gain [dB]
    tx_gain_db: float = -20.0           # TX gain [dB] — conservative default
    n_samples: int = 40_000             # samples per RX burst
    channel: str = "x1"                 # bladeRF channel identifier
    dry_run: bool = True                # True = no hardware, no RF

    # Internal log kept in dry-run mode
    _log: list[str] = field(default_factory=list, init=False, repr=False, compare=False)

    def __post_init__(self) -> None:
        validate_frequency_hz(self.center_freq_hz)
        validate_sample_rate_hz(self.sample_rate_hz)
        validate_bandwidth_hz(self.bandwidth_hz)
        validate_gain_db(self.rx_gain_db, "rx")
        validate_gain_db(self.tx_gain_db, "tx")
        validate_n_samples(self.n_samples)


# ---------------------------------------------------------------------------
# Device
# ---------------------------------------------------------------------------

class BladeRFDevice:
    """
    Hardware-abstracted interface to a bladeRF SDR.

    Parameters
    ----------
    config : BladeRFConfig
        Validated device configuration.
    confirmation : str or None
        Must equal 'CONFIRM HARDWARE RUN' when config.dry_run is False.
        Ignored in dry-run mode.
    _bladerf_module : object or None
        Internal parameter for unit tests only.  When provided, this object
        is used instead of the real bladeRF Python package (bypasses
        _import_bladerf()).  Pass a fake bladeRF module to exercise the
        real-mode code path without USB access.  Do not use in production.

    Examples
    --------
    Dry-run usage (safe, no hardware required):

        config = BladeRFConfig(center_freq_hz=2.4e9, dry_run=True)
        device = BladeRFDevice(config)
        device.configure_rx()
        iq = device.capture_rx()
        device.close()
    """

    def __init__(
        self,
        config: BladeRFConfig,
        confirmation: str | None = None,
        _bladerf_module=None,
    ) -> None:
        self._config = config
        self._configured_rx: bool = False
        self._configured_tx: bool = False
        self._closed: bool = False
        self._log: list[str] = []
        self._bladerf_mod = None
        self._device = None

        if not config.dry_run:
            require_hardware_confirmation(confirmation)
            # Re-validate (config fields may have been mutated after construction)
            validate_frequency_hz(config.center_freq_hz)
            validate_sample_rate_hz(config.sample_rate_hz)
            validate_bandwidth_hz(config.bandwidth_hz)
            validate_gain_db(config.rx_gain_db, "rx")
            validate_gain_db(config.tx_gain_db, "tx")
            validate_n_samples(config.n_samples)
            # Obtain bladeRF module: injected fake (tests) or real lazy import
            self._bladerf_mod = (
                _bladerf_module if _bladerf_module is not None
                else _import_bladerf()
            )
            # Open the bladeRF device (real USB device, or fake for tests)
            self._device = self._bladerf_mod.BladeRF()
            self._log.append("BladeRFDevice created (REAL HARDWARE)")
        else:
            self._log.append("BladeRFDevice created (DRY-RUN)")

    # -----------------------------------------------------------------------
    # Configuration
    # -----------------------------------------------------------------------

    def configure_rx(self) -> None:
        """
        Apply RX configuration to the device.

        In dry-run mode: validates parameters and logs the action.
        In real mode: sets frequency, sample rate, bandwidth, and gain on
        RX channel 0 via the libbladeRF Python bindings.
        """
        self._assert_open()
        if not self._config.dry_run:
            ch = self._device.Channel(self._bladerf_mod.CHANNEL_RX(0))
            ch.frequency = int(self._config.center_freq_hz)
            ch.sample_rate = int(self._config.sample_rate_hz)
            ch.bandwidth = int(self._config.bandwidth_hz)
            ch.gain = int(self._config.rx_gain_db)
            self._log.append(
                f"configure_rx: "
                f"f={self._config.center_freq_hz/1e6:.1f} MHz, "
                f"fs={self._config.sample_rate_hz/1e6:.1f} MS/s, "
                f"bw={self._config.bandwidth_hz/1e6:.1f} MHz, "
                f"gain={self._config.rx_gain_db:.1f} dB"
            )
        else:
            self._log.append(
                f"[DRY-RUN] configure_rx: "
                f"f={self._config.center_freq_hz/1e6:.1f} MHz, "
                f"fs={self._config.sample_rate_hz/1e6:.1f} MS/s, "
                f"bw={self._config.bandwidth_hz/1e6:.1f} MHz, "
                f"gain={self._config.rx_gain_db:.1f} dB"
            )
        self._configured_rx = True

    def configure_tx(self) -> None:
        """
        Apply TX configuration to the device.

        In dry-run mode: logs the action without enabling TX.
        In real mode: not yet implemented.

        Note: TX is not enabled even in dry-run; this method only stores the
        configuration for later inspection via status().
        """
        self._assert_open()
        if not self._config.dry_run:
            raise NotImplementedError(
                "Real TX configuration is not yet implemented.  "
                "TX must be gated by explicit CONFIRM HARDWARE RUN and a verified "
                "antenna or RF load connection before this method is safe to call."
            )
        self._log.append(
            f"[DRY-RUN] configure_tx: "
            f"f={self._config.center_freq_hz/1e6:.1f} MHz, "
            f"gain={self._config.tx_gain_db:.1f} dB  (TX not enabled)"
        )
        self._configured_tx = True

    # -----------------------------------------------------------------------
    # Capture
    # -----------------------------------------------------------------------

    def capture_rx(self) -> np.ndarray:
        """
        Capture a burst of IQ samples from the RX channel.

        In dry-run mode: returns deterministic low-amplitude synthetic noise.
        In real mode: delegates to _capture_rx_real() which uses the bladeRF
        sync RX interface and converts SC16_Q11 samples to complex128.

        Returns
        -------
        np.ndarray
            Complex IQ array of shape (n_samples,), dtype complex128.

        Raises
        ------
        RuntimeError
            If configure_rx() was not called first, or device is closed.
        """
        self._assert_open()
        if not self._configured_rx:
            raise RuntimeError("configure_rx() must be called before capture_rx().")

        if not self._config.dry_run:
            return self._capture_rx_real()

        # Dry-run: deterministic synthetic noise
        seed = int(
            (self._config.center_freq_hz / 1e6 + self._config.sample_rate_hz / 1e6)
        ) % (2**31)
        rng = np.random.default_rng(seed=seed)
        noise_amp = 0.01
        n = self._config.n_samples
        iq = (rng.standard_normal(n) + 1j * rng.standard_normal(n)) * noise_amp
        iq = iq.astype(np.complex128)
        self._log.append(
            f"[DRY-RUN] capture_rx: {n} samples, mean={np.mean(np.abs(iq)):.4f}, "
            f"std={np.std(iq):.4f}"
        )
        return iq

    def _capture_rx_real(self) -> np.ndarray:
        """
        Real hardware RX capture via libbladeRF sync interface.

        Procedure:
        1. Configure sync RX interface: SC16_Q11 format, single RX channel
           (ChannelLayout.RX_X1), 16 buffers of 8192 samples each.
        2. Allocate bytearray buffer: 4 bytes per sample (2 x int16: I, Q).
        3. Call sync_rx() to fill the buffer from the ADC stream.
        4. View buffer as int16 and convert via sc16q11_to_complex().

        NOTE: This method has NOT been executed on real hardware.  It is
        exercised only through fake-backend unit tests in this session.
        First real invocation requires a physically connected bladeRF and
        'CONFIRM HARDWARE RUN' at BladeRFDevice construction.
        """
        n = self._config.n_samples
        self._device.sync_config(
            layout=self._bladerf_mod.ChannelLayout.RX_X1,
            fmt=self._bladerf_mod.Format.SC16_Q11,
            num_buffers=16,
            buffer_size=8192,
            num_transfers=8,
            stream_timeout=3500,
        )
        # 4 bytes per sample: 2 x int16 (I and Q)
        buf = bytearray(n * 4)
        self._device.sync_rx(buf, n)
        raw = np.frombuffer(buf, dtype=np.int16)
        iq = sc16q11_to_complex(raw)
        self._log.append(
            f"capture_rx: {n} samples, "
            f"mean_amp={np.mean(np.abs(iq)):.4f}, "
            f"std={np.std(iq):.4f}"
        )
        return iq

    # -----------------------------------------------------------------------
    # Transmission
    # -----------------------------------------------------------------------

    def transmit_tone(
        self,
        freq_offset_hz: float = 0.0,
        amplitude: float = 0.0,
        duration_s: float = 0.001,
    ) -> None:
        """
        Transmit a CW tone at center_freq_hz + freq_offset_hz.

        SAFETY: In real hardware mode this method raises SafetyError — real
        transmission is not implemented in this phase.  In dry-run mode, no
        RF is emitted; the call is logged for debugging only.

        Parameters
        ----------
        freq_offset_hz : float
            Offset from center frequency [Hz].
        amplitude : float
            Relative amplitude [0–1].  Ignored in dry-run.
        duration_s : float
            Duration [s].  Ignored in dry-run.
        """
        self._assert_open()
        if not self._config.dry_run:
            raise SafetyError(
                "transmit_tone() is blocked in real hardware mode.  "
                "Real RF transmission requires a verified antenna or RF load, "
                "regulatory approval, and implementation of the TX streaming path.  "
                "Provide CONFIRM HARDWARE RUN and implement the TX stub before use."
            )
        self._log.append(
            f"[DRY-RUN] transmit_tone: f_offset={freq_offset_hz/1e3:.1f} kHz, "
            f"amp={amplitude:.3f}, dur={duration_s*1e3:.1f} ms  "
            f"(NOT TRANSMITTED — dry-run mode)"
        )

    # -----------------------------------------------------------------------
    # Lifecycle
    # -----------------------------------------------------------------------

    def close(self) -> None:
        """Release the device and mark it closed."""
        if not self._closed:
            if not self._config.dry_run and self._device is not None:
                self._device.close()
            self._log.append(
                "[DRY-RUN] close: device closed." if self._config.dry_run
                else "close: device closed."
            )
            self._closed = True

    def status(self) -> dict:
        """Return a snapshot of device configuration and state."""
        return {
            "dry_run": self._config.dry_run,
            "center_freq_hz": self._config.center_freq_hz,
            "sample_rate_hz": self._config.sample_rate_hz,
            "bandwidth_hz": self._config.bandwidth_hz,
            "rx_gain_db": self._config.rx_gain_db,
            "tx_gain_db": self._config.tx_gain_db,
            "n_samples": self._config.n_samples,
            "channel": self._config.channel,
            "configured_rx": self._configured_rx,
            "configured_tx": self._configured_tx,
            "closed": self._closed,
            "log_entries": len(self._log),
        }

    # -----------------------------------------------------------------------
    # Private helpers
    # -----------------------------------------------------------------------

    def _assert_open(self) -> None:
        if self._closed:
            raise RuntimeError("Device is already closed.  Create a new BladeRFDevice.")
