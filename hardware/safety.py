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


# ---------------------------------------------------------------------------
# TX-specific safety constants (reflector experiment)
# ---------------------------------------------------------------------------

MAX_FIRST_TX_PILOT_DURATION_S: float = 0.05        # 50 ms max for pilot burst
MAX_REFLECTOR_TX_DURATION_PER_FREQ_S: float = 0.02  # 20 ms max per frequency step
MAX_OFDM_IQ_BURST_DURATION_S: float = 0.01         # 10 ms max for OFDM IQ burst
MIN_REFLECTOR_DISTANCE_M: float = 0.5               # closer than 0.5 m is unsafe
MAX_REFLECTOR_DISTANCE_M: float = 3.0               # beyond 3 m, SNR will be very low
FIRST_TX_ALLOWED_ANTENNA_MODE: str = "antenna_reflector_test"
# bladeRF 2.0 micro TX power range is approximately -23.5 dB to +66 dB (hardware).
# For the first antenna test we cap at -20 dB (the existing conservative limit).
REFLECTOR_TX_GAIN_DB: float = -20.0


# ---------------------------------------------------------------------------
# TX experiment validation functions
# ---------------------------------------------------------------------------

class ReflectorSetupConfirmation:
    """Holds the required reflector-ready phrase for supervised TX experiments."""
    PHRASE: str = "REFLECTOR SETUP READY"


def require_reflector_setup_ready(confirmation: str | None) -> None:
    """
    Assert that the caller has confirmed the reflector setup.

    Raises
    ------
    SafetyError
        If the phrase is missing or does not match exactly.
    """
    if confirmation != ReflectorSetupConfirmation.PHRASE:
        raise SafetyError(
            f"Reflector setup confirmation requires the exact phrase "
            f"'{ReflectorSetupConfirmation.PHRASE}'. "
            f"Received: {confirmation!r}."
        )


def validate_tx_duration_s(duration_s: float, max_duration_s: float = MAX_FIRST_TX_PILOT_DURATION_S) -> None:
    """Raise SafetyError if TX duration exceeds the allowed maximum."""
    if duration_s <= 0 or duration_s > max_duration_s:
        raise SafetyError(
            f"TX duration {duration_s*1e3:.1f} ms exceeds allowed maximum "
            f"{max_duration_s*1e3:.1f} ms.  Keep TX bursts short."
        )


def validate_tx_gain_db(gain_db: float) -> None:
    """Raise SafetyError if TX gain exceeds the conservative reflector-test limit."""
    if gain_db > BLADERF_MAX_TX_GAIN_DB:
        raise SafetyError(
            f"TX gain {gain_db:.1f} dB exceeds conservative safety limit "
            f"{BLADERF_MAX_TX_GAIN_DB:.1f} dB for antenna-based experiment."
        )


def validate_tx_antenna_mode(mode: str) -> None:
    """Raise SafetyError if antenna mode is not the approved reflector-test mode."""
    if mode != FIRST_TX_ALLOWED_ANTENNA_MODE:
        raise SafetyError(
            f"TX antenna mode '{mode}' is not allowed.  "
            f"Only '{FIRST_TX_ALLOWED_ANTENNA_MODE}' is permitted for the first TX experiment."
        )


def validate_reflector_distance_m(distance_m: float) -> None:
    """Raise SafetyError if reflector distance is outside the allowed range."""
    if not (MIN_REFLECTOR_DISTANCE_M <= distance_m <= MAX_REFLECTOR_DISTANCE_M):
        raise SafetyError(
            f"Reflector distance {distance_m:.2f} m is outside the allowed range "
            f"[{MIN_REFLECTOR_DISTANCE_M:.1f}, {MAX_REFLECTOR_DISTANCE_M:.1f}] m."
        )


def validate_no_subject_flags(
    human_subject: bool,
    phantom: bool,
    biological_material: bool,
) -> None:
    """
    Raise SafetyError if any prohibited subject flag is True.

    No human subjects, phantoms, or biological material are permitted
    in the first TX reflector experiment.
    """
    if human_subject:
        raise SafetyError(
            "human_subject=True is not allowed.  "
            "No human subjects permitted in any TX experiment."
        )
    if phantom:
        raise SafetyError(
            "phantom=True is not allowed.  "
            "Phantom experiments require a separate validated protocol."
        )
    if biological_material:
        raise SafetyError(
            "biological_material=True is not allowed.  "
            "No biological material permitted in any TX experiment."
        )


def validate_no_motion_flags(motor_scan: bool, sar_scan: bool) -> None:
    """
    Raise SafetyError if any motion-related flag is True.

    No motor or SAR scan is permitted during the first TX reflector experiment.
    """
    if motor_scan:
        raise SafetyError(
            "motor_scan=True is not allowed.  "
            "Motor movement requires a separate validated protocol."
        )
    if sar_scan:
        raise SafetyError(
            "sar_scan=True is not allowed.  "
            "SAR scans require azimuth stage validation before use."
        )
