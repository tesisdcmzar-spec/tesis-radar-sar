"""
Unit tests for processing/ofdm_channel.py.

All tests use synthetic data only.
No bladeRF. No USB. No RF. No motors. No raw datasets.
"""
from __future__ import annotations

import pathlib
import numpy as np
import pytest

from processing.ofdm_channel import (
    generate_bpsk_pilots,
    generate_qpsk_pilots,
    allocate_active_subcarriers,
    make_ofdm_symbol,
    remove_cyclic_prefix,
    fft_ofdm_symbol,
    estimate_channel_rx_tx,
    channel_impulse_response,
    unwrap_phase_vs_frequency,
    estimate_group_delay,
    estimate_delay_peak,
    estimate_range_from_delay,
    simulate_ofdm_channel_from_paths,
    summarize_ofdm_channel,
)

_ROOT = pathlib.Path(__file__).resolve().parent.parent


# ---------------------------------------------------------------------------
# BPSK pilots
# ---------------------------------------------------------------------------

def test_bpsk_pilot_length():
    assert len(generate_bpsk_pilots(64)) == 64


def test_bpsk_pilot_values_are_plus_minus_one():
    X = generate_bpsk_pilots(200, seed=0)
    assert np.all(np.isin(X.real, [-1.0, 1.0]))
    assert np.allclose(X.imag, 0.0)


def test_bpsk_pilot_deterministic_with_seed():
    X1 = generate_bpsk_pilots(32, seed=7)
    X2 = generate_bpsk_pilots(32, seed=7)
    assert np.array_equal(X1, X2)


def test_bpsk_pilot_without_seed_differs():
    # Probability of collision is 2^{-256}, negligible.
    X1 = generate_bpsk_pilots(256)
    X2 = generate_bpsk_pilots(256)
    assert not np.array_equal(X1, X2)


# ---------------------------------------------------------------------------
# QPSK pilots
# ---------------------------------------------------------------------------

def test_qpsk_pilot_length():
    assert len(generate_qpsk_pilots(64, seed=0)) == 64


def test_qpsk_pilot_unit_magnitude():
    X = generate_qpsk_pilots(200, seed=0)
    assert np.allclose(np.abs(X), 1.0)


def test_qpsk_pilot_four_phases():
    X = generate_qpsk_pilots(1000, seed=0)
    phases = np.angle(X) % (2.0 * np.pi)
    expected = np.array([np.pi / 4, 3 * np.pi / 4, 5 * np.pi / 4, 7 * np.pi / 4])
    for e in expected:
        assert np.any(np.abs(phases - e) < 1e-6), f"Phase {e:.4f} not found in QPSK output"


def test_qpsk_pilot_deterministic_with_seed():
    X1 = generate_qpsk_pilots(32, seed=42)
    X2 = generate_qpsk_pilots(32, seed=42)
    assert np.array_equal(X1, X2)


# ---------------------------------------------------------------------------
# Active subcarrier allocation
# ---------------------------------------------------------------------------

def test_active_subcarriers_count_no_guard():
    # half=100; positive: 1..100 (100), negative: 156..255 (100) = 200 total
    idx = allocate_active_subcarriers(256, 200, dc_null=True, guard_bins=0)
    assert len(idx) == 200


def test_active_subcarriers_dc_excluded_by_default():
    idx = allocate_active_subcarriers(256, 200, dc_null=True)
    assert 0 not in idx


def test_active_subcarriers_dc_included_when_requested():
    idx = allocate_active_subcarriers(256, 200, dc_null=False)
    assert 0 in idx


def test_active_subcarriers_guard_bins_reduce_count():
    idx_no_guard = allocate_active_subcarriers(256, 100, dc_null=True, guard_bins=0)
    idx_guard = allocate_active_subcarriers(256, 100, dc_null=True, guard_bins=5)
    assert len(idx_guard) < len(idx_no_guard)
    # Each half loses guard_bins: total reduction = 2 * guard_bins
    assert len(idx_no_guard) - len(idx_guard) == 2 * 5


def test_active_subcarriers_all_in_valid_range():
    n_fft = 512
    idx = allocate_active_subcarriers(n_fft, 400, dc_null=True, guard_bins=2)
    assert np.all(idx >= 0)
    assert np.all(idx < n_fft)


def test_active_subcarriers_sorted():
    idx = allocate_active_subcarriers(256, 200, dc_null=True, guard_bins=4)
    assert np.all(np.diff(idx) > 0)


def test_active_subcarriers_n_active_exceeds_n_fft_raises():
    with pytest.raises(ValueError):
        allocate_active_subcarriers(64, 128)


# ---------------------------------------------------------------------------
# OFDM symbol construction
# ---------------------------------------------------------------------------

def test_make_ofdm_symbol_output_length():
    n_fft, cp_len = 64, 16
    tx = make_ofdm_symbol(np.ones(n_fft, dtype=complex), n_fft, cp_len)
    assert len(tx) == n_fft + cp_len


def test_cp_is_suffix_of_ofdm_body():
    rng = np.random.default_rng(0)
    n_fft, cp_len = 64, 16
    X = rng.standard_normal(n_fft) + 1j * rng.standard_normal(n_fft)
    tx = make_ofdm_symbol(X, n_fft, cp_len)
    # tx[:cp_len] is CP, tx[n_fft:] is the last cp_len samples of the body
    assert np.allclose(tx[:cp_len], tx[n_fft:])


def test_make_ofdm_symbol_zero_cp():
    n_fft = 32
    tx = make_ofdm_symbol(np.ones(n_fft, dtype=complex), n_fft, cp_len=0)
    assert len(tx) == n_fft


def test_make_ofdm_symbol_wrong_freq_domain_length_raises():
    with pytest.raises(ValueError):
        make_ofdm_symbol(np.ones(10, dtype=complex), n_fft=64, cp_len=16)


def test_make_ofdm_symbol_negative_cp_raises():
    with pytest.raises(ValueError):
        make_ofdm_symbol(np.ones(32, dtype=complex), n_fft=32, cp_len=-1)


# ---------------------------------------------------------------------------
# Cyclic prefix removal
# ---------------------------------------------------------------------------

def test_remove_cp_output_length():
    n_fft, cp_len = 64, 16
    out = remove_cyclic_prefix(np.ones(n_fft + cp_len, dtype=complex), cp_len, n_fft)
    assert len(out) == n_fft


def test_remove_cp_returns_correct_slice():
    n_fft, cp_len = 64, 16
    rx = np.arange(n_fft + cp_len, dtype=complex)
    out = remove_cyclic_prefix(rx, cp_len, n_fft)
    assert np.allclose(out, rx[cp_len: cp_len + n_fft])


def test_remove_cp_too_short_raises():
    with pytest.raises(ValueError):
        remove_cyclic_prefix(np.ones(10, dtype=complex), cp_len=16, n_fft=64)


# ---------------------------------------------------------------------------
# FFT / IFFT round-trip
# ---------------------------------------------------------------------------

def test_fft_ifft_round_trip():
    rng = np.random.default_rng(0)
    n_fft = 128
    X_orig = rng.standard_normal(n_fft) + 1j * rng.standard_normal(n_fft)
    # make_ofdm_symbol: IFFT; remove_cyclic_prefix + fft_ofdm_symbol: FFT
    tx = make_ofdm_symbol(X_orig, n_fft, cp_len=0)
    X_recovered = fft_ofdm_symbol(remove_cyclic_prefix(tx, 0, n_fft))
    assert np.allclose(X_orig, X_recovered, atol=1e-10)


# ---------------------------------------------------------------------------
# Channel estimation
# ---------------------------------------------------------------------------

def test_estimate_channel_recovers_known_H():
    rng = np.random.default_rng(42)
    n = 64
    H_true = rng.standard_normal(n) + 1j * rng.standard_normal(n)
    X = rng.standard_normal(n) + 1j * rng.standard_normal(n)
    Y = H_true * X
    H_est = estimate_channel_rx_tx(Y, X)
    assert np.allclose(H_est, H_true, atol=1e-10)


def test_estimate_channel_inactive_pilots_yield_zero_H():
    X = np.zeros(16, dtype=complex)
    Y = np.ones(16, dtype=complex)
    H = estimate_channel_rx_tx(Y, X, eps=1e-12)
    assert np.allclose(H, 0.0)


def test_estimate_channel_shape_mismatch_raises():
    with pytest.raises(ValueError):
        estimate_channel_rx_tx(np.ones(8, dtype=complex), np.ones(16, dtype=complex))


# ---------------------------------------------------------------------------
# Channel impulse response
# ---------------------------------------------------------------------------

def test_cir_output_length():
    H = np.ones(64, dtype=complex)
    assert len(channel_impulse_response(H)) == 64


def test_cir_peak_at_expected_bin():
    # H[k] = exp(-j*2*pi*k*d/N) => IFFT has a unit impulse at bin d
    n = 256
    d = 20
    k = np.arange(n)
    H = np.exp(-1j * 2.0 * np.pi * k * d / n)
    cir = channel_impulse_response(H, window="none")
    assert int(np.argmax(np.abs(cir))) == d


# ---------------------------------------------------------------------------
# Phase unwrapping
# ---------------------------------------------------------------------------

def test_unwrap_phase_monotone_for_increasing_phase():
    n = 64
    H = np.exp(1j * np.linspace(0.0, 8.0 * np.pi, n))
    phase = unwrap_phase_vs_frequency(H)
    assert np.all(np.diff(phase) >= 0)


# ---------------------------------------------------------------------------
# Group delay
# ---------------------------------------------------------------------------

def test_group_delay_constant_for_single_path():
    tau = 10e-9  # 10 ns one-way
    freqs = np.linspace(2.3e9, 2.5e9, 201)
    H = np.exp(-1j * 2.0 * np.pi * freqs * tau)
    gd = estimate_group_delay(freqs, H)
    # Avoid edge effects from numerical gradient
    assert np.allclose(gd[10:-10], tau, rtol=1e-3)


# ---------------------------------------------------------------------------
# Delay estimation
# ---------------------------------------------------------------------------

def test_estimate_delay_peak_single_path():
    fs = 20e6
    n = 256
    d_bins = 10
    delay_expected = d_bins / fs
    k = np.arange(n)
    H = np.exp(-1j * 2.0 * np.pi * k * d_bins / n)
    cir = channel_impulse_response(H, window="none")
    delay_est = estimate_delay_peak(cir, fs)
    assert abs(delay_est - delay_expected) < 1e-9


# ---------------------------------------------------------------------------
# Range from delay
# ---------------------------------------------------------------------------

def test_range_from_delay_two_way():
    # 10 ns two-way -> 1.5 m
    r = estimate_range_from_delay(10e-9, c=3e8, two_way=True)
    assert abs(r - 1.5) < 1e-6


def test_range_from_delay_one_way():
    # 10 ns one-way -> 3.0 m
    r = estimate_range_from_delay(10e-9, c=3e8, two_way=False)
    assert abs(r - 3.0) < 1e-6


# ---------------------------------------------------------------------------
# Simulate channel from paths
# ---------------------------------------------------------------------------

def test_simulate_channel_single_path_matches_formula():
    freqs = np.linspace(2.3e9, 2.5e9, 11)
    R = 1.0  # 1 m
    H = simulate_ofdm_channel_from_paths(freqs, [(1.0, R)], two_way=True)
    expected = np.exp(-1j * 4.0 * np.pi * freqs * R / 3e8)
    assert np.allclose(H, expected, atol=1e-10)


def test_simulate_channel_zero_range_is_flat():
    freqs = np.linspace(1e9, 3e9, 51)
    H = simulate_ofdm_channel_from_paths(freqs, [(1.0, 0.0)], two_way=True)
    assert np.allclose(H, 1.0, atol=1e-10)


def test_simulate_channel_two_paths_output_shape():
    freqs = np.linspace(2.3e9, 2.5e9, 201)
    H = simulate_ofdm_channel_from_paths(
        freqs, [(1.0, 1.0), (0.5, 2.0)], two_way=True
    )
    assert H.shape == (201,)
    assert np.any(np.abs(H) > 0)


# ---------------------------------------------------------------------------
# Summarize channel
# ---------------------------------------------------------------------------

def test_summarize_channel_returns_required_keys():
    H = np.ones(64, dtype=complex)
    s = summarize_ofdm_channel(H)
    for key in ("n_subcarriers", "mag_mean", "mag_max", "mag_min",
                "cir_peak_idx", "cir_peak_magnitude", "phase_range_rad"):
        assert key in s, f"Missing key: {key}"


def test_summarize_channel_with_sample_rate_includes_delay_and_range():
    H = np.ones(64, dtype=complex)
    s = summarize_ofdm_channel(H, sample_rate_hz=20e6)
    assert "delay_s" in s
    assert "range_m" in s


def test_summarize_channel_with_freqs_includes_group_delay():
    freqs = np.linspace(2.3e9, 2.5e9, 64)
    H = np.ones(64, dtype=complex)
    s = summarize_ofdm_channel(H, freqs_hz=freqs)
    assert "group_delay_mean_s" in s


# ---------------------------------------------------------------------------
# No hardware imports
# ---------------------------------------------------------------------------

def test_no_hardware_import_in_ofdm_channel():
    src = (_ROOT / "processing" / "ofdm_channel.py").read_text(encoding="utf-8")
    forbidden = ["bladerf", "from hardware", "import hardware",
                 "serial", "usb.core"]
    for term in forbidden:
        assert term not in src, f"Forbidden dependency found: {term!r}"
