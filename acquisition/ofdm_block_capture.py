"""
OFDM block capture abstraction for UWB-OFDM-SAR.

Hardware-independent by default. All paths that touch a real device are
guarded by dry_run=True and require explicit confirmation strings.
Testable with fake backends and synthetic data without any bladeRF import.

Architecture context
--------------------
A single OFDM block captures H[k] over n_active subcarriers within one
bladeRF instantaneous bandwidth. Multiple blocks at different center
frequencies are later stitched by processing/ofdm_block_stitcher.py to
form a wideband channel estimate H(f).

Channel estimation per block:
    H[k] = Y[k] / X[k]
where X[k] is the known pilot symbol and Y[k] = FFT(rx[cp:cp+N_fft]).

No hardware is imported here. The caller provides a device object that
exposes configure_tx(), configure_rx(), transmit_iq_burst(), capture_rx(),
and close(). A fake device class is sufficient for all tests.
"""
from __future__ import annotations

import time
from dataclasses import dataclass, field

import numpy as np

from processing.ofdm_channel import (
    allocate_active_subcarriers,
    estimate_channel_rx_tx,
    fft_ofdm_symbol,
    generate_bpsk_pilots,
    generate_qpsk_pilots,
    make_ofdm_symbol,
    remove_cyclic_prefix,
    channel_impulse_response,
    estimate_delay_peak,
    estimate_range_from_delay,
)

__all__ = [
    "OFDMBlockConfig",
    "OFDMBlockResult",
    "build_known_ofdm_frame",
    "estimate_h_from_rx_frame",
    "capture_ofdm_block",
    "validate_ofdm_block_config",
    "summarize_ofdm_block_result",
]


# ---------------------------------------------------------------------------
# Configuration
# ---------------------------------------------------------------------------

@dataclass
class OFDMBlockConfig:
    """
    Configuration for a single OFDM block capture.

    All fields correspond to one center-frequency block.  For UWB stitching,
    multiple configs at different center_freq_hz values are used.

    Fields
    ------
    center_freq_hz  : RF center frequency for this block [Hz].
    sample_rate_hz  : ADC/DAC sample rate [samples/s].
    bandwidth_hz    : Analog filter bandwidth [Hz] (<= sample_rate_hz).
    n_fft           : OFDM DFT size.
    n_active        : Active subcarriers before guard removal.
    cp_len          : Cyclic prefix length [samples].
    guard_bins      : Guard bins removed from each edge of active region.
    dc_null         : Null DC subcarrier (bin 0) if True.
    pilot_type      : 'bpsk' or 'qpsk'.
    pilot_seed      : RNG seed for pilot generation (reproducibility).
    repetitions     : Number of OFDM symbols to average for H[k] estimation.
    tx_gain_db      : TX gain [dB]. Must satisfy safety limit.
    rx_gain_db      : RX gain [dB].
    human_subject   : Must be False.
    phantom         : Must be False.
    biological_material : Must be False.
    motor_scan      : Must be False.
    sar_scan        : Must be False.
    """

    center_freq_hz: float = 2.4e9
    sample_rate_hz: float = 2e6
    bandwidth_hz: float = 2e6
    n_fft: int = 256
    n_active: int = 160
    cp_len: int = 64
    guard_bins: int = 20
    dc_null: bool = True
    pilot_type: str = "bpsk"
    pilot_seed: int = 42
    repetitions: int = 8
    tx_gain_db: float = -20.0
    rx_gain_db: float = 20.0
    human_subject: bool = False
    phantom: bool = False
    biological_material: bool = False
    motor_scan: bool = False
    sar_scan: bool = False


@dataclass
class OFDMBlockResult:
    """
    Result of a single OFDM block capture or simulation.

    Fields
    ------
    config          : The OFDMBlockConfig used.
    H               : Channel estimate array, shape (n_fft,). Zero at inactive bins.
    active_indices  : Active subcarrier indices used for H[k].
    freqs_hz        : Absolute RF frequencies [Hz] for each active subcarrier.
    H_active        : H[k] restricted to active subcarriers, shape (n_active_actual,).
    cir             : Channel impulse response via windowed IFFT of H.
    delay_s         : Estimated propagation delay from CIR peak [s].
    range_m         : Estimated one-way range from delay [m].
    n_symbols_used  : Number of OFDM symbols averaged.
    timestamp_utc   : UTC timestamp string when result was created.
    dry_run         : True if no real hardware was used.
    metadata        : Arbitrary key-value metadata dict.
    """

    config: OFDMBlockConfig
    H: np.ndarray
    active_indices: np.ndarray
    freqs_hz: np.ndarray
    H_active: np.ndarray
    cir: np.ndarray
    delay_s: float
    range_m: float
    n_symbols_used: int
    timestamp_utc: str
    dry_run: bool
    metadata: dict = field(default_factory=dict)


# ---------------------------------------------------------------------------
# Validation
# ---------------------------------------------------------------------------

def validate_ofdm_block_config(config: OFDMBlockConfig) -> None:
    """
    Raise ValueError or SafetyError if config fields violate hard constraints.

    Does not import bladeRF. Safe to call without hardware.
    """
    if config.n_fft < 16:
        raise ValueError(f"n_fft={config.n_fft} is too small (min 16).")
    if config.n_active > config.n_fft:
        raise ValueError(
            f"n_active={config.n_active} must be <= n_fft={config.n_fft}."
        )
    if config.cp_len < 0:
        raise ValueError(f"cp_len={config.cp_len} must be >= 0.")
    if config.guard_bins < 0:
        raise ValueError(f"guard_bins={config.guard_bins} must be >= 0.")
    if config.pilot_type not in ("bpsk", "qpsk"):
        raise ValueError(
            f"pilot_type={config.pilot_type!r} must be 'bpsk' or 'qpsk'."
        )
    if config.repetitions < 1:
        raise ValueError(f"repetitions={config.repetitions} must be >= 1.")
    if config.sample_rate_hz <= 0:
        raise ValueError(f"sample_rate_hz must be > 0.")
    if config.bandwidth_hz <= 0:
        raise ValueError(f"bandwidth_hz must be > 0.")
    if config.human_subject:
        raise ValueError("human_subject=True is not allowed.")
    if config.phantom:
        raise ValueError("phantom=True is not allowed.")
    if config.biological_material:
        raise ValueError("biological_material=True is not allowed.")
    if config.motor_scan:
        raise ValueError("motor_scan=True is not allowed.")
    if config.sar_scan:
        raise ValueError("sar_scan=True is not allowed.")


# ---------------------------------------------------------------------------
# Frame construction
# ---------------------------------------------------------------------------

def build_known_ofdm_frame(config: OFDMBlockConfig) -> tuple[np.ndarray, np.ndarray]:
    """
    Build a time-domain OFDM frame and the corresponding TX frequency vector.

    Returns a single OFDM symbol repeated config.repetitions times.  All
    active subcarriers carry a known pilot (BPSK or QPSK); inactive subcarriers
    are zero.

    No hardware required.

    Parameters
    ----------
    config : OFDMBlockConfig

    Returns
    -------
    tx_time : complex array, shape (repetitions * (cp_len + n_fft),).
              Time-domain TX frame (CP included for each symbol).
    tx_freq : complex array, shape (n_fft,).
              Known frequency-domain pilot vector for one symbol.
    """
    validate_ofdm_block_config(config)

    active_idx = allocate_active_subcarriers(
        config.n_fft, config.n_active,
        dc_null=config.dc_null,
        guard_bins=config.guard_bins,
    )
    n_active_actual = len(active_idx)

    if config.pilot_type == "bpsk":
        pilots = generate_bpsk_pilots(n_active_actual, seed=config.pilot_seed)
    else:
        pilots = generate_qpsk_pilots(n_active_actual, seed=config.pilot_seed)

    # Build full FFT bin vector
    tx_freq = np.zeros(config.n_fft, dtype=complex)
    tx_freq[active_idx] = pilots

    # Build one time-domain symbol with CP
    symbol_td = make_ofdm_symbol(tx_freq, config.n_fft, config.cp_len)

    # Repeat for all repetitions
    tx_time = np.tile(symbol_td, config.repetitions)

    return tx_time, tx_freq


# ---------------------------------------------------------------------------
# Channel estimation from received frame
# ---------------------------------------------------------------------------

def estimate_h_from_rx_frame(
    rx_iq: np.ndarray,
    tx_freq_symbols: np.ndarray,
    config: OFDMBlockConfig,
) -> np.ndarray:
    """
    Estimate H[k] by averaging per-symbol channel estimates over repetitions.

    Strips the CP from each received symbol, computes FFT, then divides by the
    known pilot to get H[k] = Y[k] / X[k].  Averages over all repetitions.

    No hardware required.

    Parameters
    ----------
    rx_iq         : complex array, shape >= (repetitions * (cp_len + n_fft),).
                    Received baseband IQ samples.
    tx_freq_symbols : complex array, shape (n_fft,).
                    Known transmitted frequency-domain pilot for one symbol.
    config        : OFDMBlockConfig.

    Returns
    -------
    H : complex array, shape (n_fft,). Zero at inactive subcarriers.
    """
    sym_len = config.cp_len + config.n_fft
    H_acc = np.zeros(config.n_fft, dtype=complex)

    for rep in range(config.repetitions):
        start = rep * sym_len
        rx_sym = rx_iq[start: start + sym_len]
        if len(rx_sym) < sym_len:
            break
        rx_no_cp = remove_cyclic_prefix(rx_sym, config.cp_len, config.n_fft)
        Y = fft_ofdm_symbol(rx_no_cp)
        H_rep = estimate_channel_rx_tx(Y, tx_freq_symbols)
        H_acc += H_rep

    H = H_acc / config.repetitions
    return H


# ---------------------------------------------------------------------------
# Subcarrier frequency mapping
# ---------------------------------------------------------------------------

def _active_freqs_hz(active_idx: np.ndarray, config: OFDMBlockConfig) -> np.ndarray:
    """
    Map active subcarrier indices to absolute RF frequencies [Hz].

    Subcarrier spacing df = sample_rate_hz / n_fft.
    Positive bins [1..N/2-1] -> center_freq + k*df.
    Negative bins [N/2..N-1] -> center_freq + (k - N_fft)*df.
    """
    df = config.sample_rate_hz / config.n_fft
    n = config.n_fft
    shifts = np.where(active_idx <= n // 2, active_idx, active_idx - n).astype(float)
    return config.center_freq_hz + shifts * df


# ---------------------------------------------------------------------------
# Block capture
# ---------------------------------------------------------------------------

def capture_ofdm_block(
    device,
    config: OFDMBlockConfig,
    dry_run: bool = True,
    confirmation: str | None = None,
    reflector_setup_ready: str | None = None,
) -> OFDMBlockResult:
    """
    Capture one OFDM block: build frame, [TX+]RX, estimate H[k].

    When dry_run=True (default):
    - Uses the device's dry-run RX path (no real hardware).
    - If the device has transmit_iq_burst, calls it in dry-run mode only.
    - No real RF is emitted.

    When dry_run=False:
    - Requires confirmation='CONFIRM HARDWARE RUN'.
    - Calls device.transmit_iq_burst() with the generated OFDM frame.
    - Calls device.capture_rx() to get the real RX samples.
    - TX is automatically disabled by the device's finally block.

    H[k] is estimated by averaging over config.repetitions OFDM symbols.

    Parameters
    ----------
    device              : Object with configure_tx(), configure_rx(),
                          transmit_iq_burst(), capture_rx(), and close().
    config              : OFDMBlockConfig.
    dry_run             : If True, no real hardware access.
    confirmation        : Required confirmation phrase for real hardware.
    reflector_setup_ready : Required phrase for real TX.

    Returns
    -------
    OFDMBlockResult
    """
    validate_ofdm_block_config(config)

    if not dry_run and confirmation != "CONFIRM HARDWARE RUN":
        from hardware.safety import SafetyError
        raise SafetyError(
            "Real hardware capture requires confirmation='CONFIRM HARDWARE RUN'."
        )

    tx_time, tx_freq = build_known_ofdm_frame(config)
    n_rx_needed = len(tx_time)

    # --- RX capture ---
    if dry_run:
        # Simulate RX through a trivial channel (AWGN only, H[k]=1 at active bins)
        active_idx = allocate_active_subcarriers(
            config.n_fft, config.n_active,
            dc_null=config.dc_null,
            guard_bins=config.guard_bins,
        )
        rng = np.random.default_rng(seed=config.pilot_seed + 1)
        noise = (rng.standard_normal(n_rx_needed) + 1j * rng.standard_normal(n_rx_needed)) * 0.01
        rx_iq = tx_time + noise
    else:
        device.configure_tx()
        device.configure_rx()
        device.transmit_iq_burst(
            tx_time,
            reflector_setup_ready=reflector_setup_ready,
            human_subject=config.human_subject,
            phantom=config.phantom,
            biological_material=config.biological_material,
            motor_scan=config.motor_scan,
            sar_scan=config.sar_scan,
        )
        rx_raw = device.capture_rx()
        # Use only the samples we need
        rx_iq = rx_raw[:n_rx_needed] if len(rx_raw) >= n_rx_needed else np.pad(
            rx_raw, (0, n_rx_needed - len(rx_raw))
        )

    H = estimate_h_from_rx_frame(rx_iq, tx_freq, config)

    active_idx = allocate_active_subcarriers(
        config.n_fft, config.n_active,
        dc_null=config.dc_null,
        guard_bins=config.guard_bins,
    )
    freqs_hz = _active_freqs_hz(active_idx, config)
    H_active = H[active_idx]

    cir = channel_impulse_response(H)
    delay_s = estimate_delay_peak(cir, config.sample_rate_hz)
    range_m = estimate_range_from_delay(delay_s, two_way=True)

    return OFDMBlockResult(
        config=config,
        H=H,
        active_indices=active_idx,
        freqs_hz=freqs_hz,
        H_active=H_active,
        cir=cir,
        delay_s=delay_s,
        range_m=range_m,
        n_symbols_used=config.repetitions,
        timestamp_utc=time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
        dry_run=dry_run,
        metadata={},
    )


# ---------------------------------------------------------------------------
# Result summary
# ---------------------------------------------------------------------------

def summarize_ofdm_block_result(result: OFDMBlockResult) -> str:
    """
    Return a human-readable ASCII summary of an OFDMBlockResult.

    Safe for Windows cp1252 console output. No Unicode arrows or special chars.
    """
    cfg = result.config
    n_act = len(result.active_indices)
    mag = np.abs(result.H_active)
    mag_mean = float(np.mean(mag)) if n_act > 0 else 0.0
    mag_max = float(np.max(mag)) if n_act > 0 else 0.0
    mag_db_range = (
        20.0 * np.log10(mag_max / max(float(np.min(mag)), 1e-15))
        if mag_max > 0 and n_act > 0 else 0.0
    )
    freq_min = float(np.min(result.freqs_hz)) / 1e6 if n_act > 0 else 0.0
    freq_max = float(np.max(result.freqs_hz)) / 1e6 if n_act > 0 else 0.0

    lines = [
        "OFDM Block Result Summary",
        "=" * 40,
        f"  center_freq   : {cfg.center_freq_hz/1e6:.1f} MHz",
        f"  sample_rate   : {cfg.sample_rate_hz/1e6:.2f} MS/s",
        f"  n_fft         : {cfg.n_fft}",
        f"  active bins   : {n_act}",
        f"  freq range    : {freq_min:.3f} -- {freq_max:.3f} MHz",
        f"  repetitions   : {result.n_symbols_used}",
        f"  dry_run       : {result.dry_run}",
        f"  |H| mean      : {mag_mean:.4f}",
        f"  |H| max       : {mag_max:.4f}",
        f"  |H| dB range  : {mag_db_range:.1f} dB",
        f"  CIR peak idx  : {int(np.argmax(np.abs(result.cir)))}",
        f"  est delay     : {result.delay_s*1e9:.1f} ns",
        f"  est range     : {result.range_m*100:.1f} cm",
        f"  timestamp     : {result.timestamp_utc}",
    ]
    return "\n".join(lines)
