"""
Hardware safety layer for bladeRF operations.

All hardware validation passes through this module.  Never bypass it.
"""
from __future__ import annotations


# ---------------------------------------------------------------------------
# Exceptions
# ---------------------------------------------------------------------------

class SafetyError(Exception):
    """Raised when a requested hardware operation violates a safety constraint."""


# ---------------------------------------------------------------------------
# Confirmation protocol
# ---------------------------------------------------------------------------

class HardwareConfirmation:
    """Holds the required confirmation phrase for real hardware operations."""

    PHRASE: str = "CONFIRM HARDWARE RUN"


def require_hardware_confirmation(confirmation: str | None) -> None:
    """
    Assert that the caller has explicitly confirmed real hardware access.

    Must be called before any real RF transmission or RX streaming begins.
    The confirmation is not persistent: it must be supplied in every session
    where real hardware is used.

    Parameters
    ----------
    confirmation : str or None
        Must equal HardwareConfirmation.PHRASE exactly.

    Raises
    ------
    SafetyError
        If the confirmation is missing or incorrect.
    """
    if confirmation != HardwareConfirmation.PHRASE:
        raise SafetyError(
            f"Real hardware mode requires the exact confirmation string "
            f"'{HardwareConfirmation.PHRASE}'. "
            f"Received: {confirmation!r}.  "
            f"This confirmation is not persistent between sessions."
        )


# ---------------------------------------------------------------------------
# Safe operating limits — bladeRF 2.0 micro (conservative defaults)
# ---------------------------------------------------------------------------

BLADERF_MIN_FREQ_HZ: float = 70e6       # 70 MHz
BLADERF_MAX_FREQ_HZ: float = 6e9        # 6 GHz
BLADERF_MAX_SAMPLE_RATE_HZ: float = 61.44e6   # 61.44 MS/s
BLADERF_MAX_BANDWIDTH_HZ: float = 56e6  # 56 MHz
BLADERF_MAX_TX_GAIN_DB: float = -20.0   # conservative; prevents accidental high power
BLADERF_MAX_RX_GAIN_DB: float = 60.0    # typical bladeRF RX gain range
BLADERF_MAX_CAPTURE_SAMPLES: int = 10_000_000   # 10 M samples per burst


# ---------------------------------------------------------------------------
# Validation functions
# ---------------------------------------------------------------------------

def validate_frequency_hz(freq_hz: float) -> None:
    """Raise SafetyError if freq_hz is outside the bladeRF supported range."""
    if not (BLADERF_MIN_FREQ_HZ <= freq_hz <= BLADERF_MAX_FREQ_HZ):
        raise SafetyError(
            f"Frequency {freq_hz/1e6:.3f} MHz is outside the safe operating range "
            f"[{BLADERF_MIN_FREQ_HZ/1e6:.0f} MHz, {BLADERF_MAX_FREQ_HZ/1e9:.0f} GHz]."
        )


def validate_sample_rate_hz(sample_rate_hz: float) -> None:
    """Raise SafetyError if sample_rate_hz exceeds the bladeRF maximum."""
    if sample_rate_hz <= 0 or sample_rate_hz > BLADERF_MAX_SAMPLE_RATE_HZ:
        raise SafetyError(
            f"Sample rate {sample_rate_hz/1e6:.3f} MS/s is outside the safe range "
            f"(0, {BLADERF_MAX_SAMPLE_RATE_HZ/1e6:.2f}] MS/s."
        )


def validate_bandwidth_hz(bandwidth_hz: float) -> None:
    """Raise SafetyError if bandwidth_hz exceeds the bladeRF maximum."""
    if bandwidth_hz <= 0 or bandwidth_hz > BLADERF_MAX_BANDWIDTH_HZ:
        raise SafetyError(
            f"Bandwidth {bandwidth_hz/1e6:.3f} MHz is outside the safe range "
            f"(0, {BLADERF_MAX_BANDWIDTH_HZ/1e6:.0f}] MHz."
        )


def validate_gain_db(gain_db: float, kind: str) -> None:
    """
    Raise SafetyError if gain_db violates the limit for the given channel kind.

    Parameters
    ----------
    gain_db : float
        Requested gain in dBm (TX) or dB (RX).
    kind : str
        'tx' or 'rx'.
    """
    kind = kind.lower()
    if kind == "tx":
        if gain_db > BLADERF_MAX_TX_GAIN_DB:
            raise SafetyError(
                f"TX gain {gain_db:.1f} dB exceeds conservative safety limit "
                f"{BLADERF_MAX_TX_GAIN_DB:.1f} dB.  "
                f"Increase limit only after verifying antenna load and regulatory compliance."
            )
    elif kind == "rx":
        if gain_db < 0 or gain_db > BLADERF_MAX_RX_GAIN_DB:
            raise SafetyError(
                f"RX gain {gain_db:.1f} dB is outside the safe range "
                f"[0, {BLADERF_MAX_RX_GAIN_DB:.0f}] dB."
            )
    else:
        raise ValueError(f"kind must be 'tx' or 'rx', got {kind!r}.")


def validate_n_samples(n_samples: int) -> None:
    """Raise SafetyError if n_samples exceeds the per-burst safety limit."""
    if n_samples <= 0 or n_samples > BLADERF_MAX_CAPTURE_SAMPLES:
        raise SafetyError(
            f"n_samples={n_samples} is outside the safe range "
            f"(0, {BLADERF_MAX_CAPTURE_SAMPLES:,}].  "
            f"Request smaller bursts or increase limit deliberately."
        )
