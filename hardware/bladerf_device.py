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
   imported inside methods, only when dry_run=False AND confirmation has been
   validated.  This ensures tests and offline scripts never trigger USB access
   by accident.

4. transmit_tone() always raises SafetyError when dry_run=False (not yet
   implemented).  In dry-run mode it simulates logging without emitting RF.

Current status
--------------
Real hardware methods are stubs (raise NotImplementedError).  They will be
implemented in a later phase after the safety gate and lab procedures are
established.
"""
from __future__ import annotations

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
# Configuration
# ---------------------------------------------------------------------------

@dataclass
class BladeRFConfig:
    """
    Validated configuration for a single bladeRF capture session.

    All parameters are validated against safe limits on construction when
    validate=True (the default).  Parameters are also validated again inside
    BladeRFDevice.__init__() to catch any post-construction mutations.
    """

    center_freq_hz: float = 2.4e9       # RX (and TX if enabled) center frequency [Hz]
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

    Examples
    --------
    Dry-run usage (safe, no hardware required):

        config = BladeRFConfig(center_freq_hz=2.4e9, dry_run=True)
        device = BladeRFDevice(config)
        device.configure_rx()
        iq = device.capture_rx()
        device.close()
    """

    def __init__(self, config: BladeRFConfig, confirmation: str | None = None) -> None:
        if not config.dry_run:
            require_hardware_confirmation(confirmation)
            # Re-validate (config fields may have been mutated after construction)
            validate_frequency_hz(config.center_freq_hz)
            validate_sample_rate_hz(config.sample_rate_hz)
            validate_bandwidth_hz(config.bandwidth_hz)
            validate_gain_db(config.rx_gain_db, "rx")
            validate_gain_db(config.tx_gain_db, "tx")
            validate_n_samples(config.n_samples)

        self._config = config
        self._configured_rx: bool = False
        self._configured_tx: bool = False
        self._closed: bool = False
        self._log: list[str] = []

        mode = "DRY-RUN" if config.dry_run else "REAL HARDWARE"
        self._log.append(f"BladeRFDevice created ({mode})")

    # -----------------------------------------------------------------------
    # Configuration
    # -----------------------------------------------------------------------

    def configure_rx(self) -> None:
        """
        Apply RX configuration to the device.

        In dry-run mode: validates parameters and logs the action.
        In real mode: not yet implemented.
        """
        self._assert_open()
        if not self._config.dry_run:
            raise NotImplementedError(
                "Real RX configuration is not yet implemented.  "
                "Implement hardware/bladerf_device.py with libbladeRF bindings "
                "after safety procedures are established."
            )
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

        Returns
        -------
        np.ndarray
            Complex IQ array of shape (n_samples,), dtype complex128.
            In dry-run mode: deterministic low-amplitude synthetic noise.

        Raises
        ------
        RuntimeError
            If configure_rx() was not called first, or device is closed.
        NotImplementedError
            If dry_run=False (real capture not yet implemented).
        """
        self._assert_open()
        if not self._configured_rx:
            raise RuntimeError("configure_rx() must be called before capture_rx().")

        if not self._config.dry_run:
            raise NotImplementedError(
                "Real RX capture is not yet implemented.  "
                "libbladeRF streaming will be added in the next hardware phase."
            )

        # Deterministic synthetic noise — seed derived from key config params
        seed = int((self._config.center_freq_hz / 1e6 + self._config.sample_rate_hz / 1e6)) % (2**31)
        rng = np.random.default_rng(seed=seed)
        noise_amp = 0.01   # low amplitude to represent thermal noise floor
        n = self._config.n_samples
        iq = (rng.standard_normal(n) + 1j * rng.standard_normal(n)) * noise_amp
        iq = iq.astype(np.complex128)

        self._log.append(
            f"[DRY-RUN] capture_rx: {n} samples, mean={np.mean(np.abs(iq)):.4f}, "
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
        # Dry-run: log only, no RF
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
            if not self._config.dry_run:
                # Stub: would call bladerf.close() or equivalent
                pass
            self._log.append("[DRY-RUN] close: device closed." if self._config.dry_run
                             else "close: device closed.")
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
