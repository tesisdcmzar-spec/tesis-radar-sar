# Legacy Script Inventory

Read-only reference. Do NOT edit these files.
They are the source of truth for known-good bladeRF hardware parameters.

| File | Category | Description |
|------|----------|-------------|
| `test_conexion.py` | connection | Opens bladeRF, prints board name and serial, loads FPGA from a path (requires editing the FPGA path before use). |
| `tst_conexión.py` | info / RX | Low-level `_bladerf` API connection check: prints device list, library/firmware/FPGA versions, RX channel ranges and gain modes. |
| `informacion.py` | TX | Transmits a 1 MHz tone at 100 MHz center, 10 MHz SR, gain 0 dB, repeated 30×; earliest working TX example. |
| `test_emision.py` | TX | Cleaner TX tone script with try/finally safety block; same parameters as `informacion.py` but with proper USB release. |
| `test_captura_blog.py` | RX | Captures 1 M samples at 100 MHz / 10 MHz SR / 60 dB gain; plots first 1000 IQ samples in time domain. |
| `test_captura.py` | RX / plot | RX capture at 95.5 MHz / 2 MHz SR; removes DC offset; plots spectrum in dBFS. |
| `test_captura_tiempo.py` | (empty) | Placeholder — file is essentially empty (1 line). No usable content. |
| `test_barrido_frec_captura.py` | sweep / RX | RX-only frequency sweep 100 MHz→6 GHz, 60 MHz step, 40 MHz SR/BW, 40 000 samples/step; saves one `.npy` per step; reports LO and capture timing. Uses compat hack for enum constants. |
| `test_barrido_frec_emision.py` | sweep / TX | TX-only frequency sweep (same range/step); transmits zeros (carrier leakage baseline); benchmarks LO tune + TX transfer time. |
| `test_txrx_blog.py` | full-duplex | Single full-duplex capture at 1 GHz / 40 MHz SR using two threads synchronized with `threading.Event`; saves to `captura_fullduplex.npy`. |
| `test_barrido_frec_txrx.py` | sweep / full-duplex | Full-duplex frequency sweep 100 MHz→6 GHz, 60 MHz step; TX zeros + RX capture per step; saves per-step `.npy`; comprehensive timing report. |
| `test_fullduplex_señal_offset.py` | sweep / full-duplex | Same sweep as above but TX transmits a 5 MHz offset tone (not zeros); used to verify RX can capture a known signal across the band. |
| `BladeRF_Sweep_Benchmark.py` | benchmark | Tests step sizes 10–60 MHz over the full band; measures total wall-clock sweep time; generates a timing-vs-step-size plot saved as PNG. |
| `visor_espectro.py` | plot | Loads a `.npy` IQ file, removes DC, computes FFT, plots spectrum in dB with a 5 MHz reference line. |
| `generador_simbolo_maestro.py` | OFDM / simulation | Generates an 824-active-subcarrier OFDM pilot symbol (N=1024, 60 MHz BW, 100 guard bins, random phases seed=42); saves time- and frequency-domain `.npy` files. |
| `bladerf1 - tx.py` | OFDM / TX | Transmits a 1024-subcarrier OFDM symbol with cyclic prefix at 2400 MHz / 40 MHz SR in a continuous loop; uses `_bladerf` + `BladeRF` mixed import. |
| `bladerf2 - rx.py` | OFDM / RX | Captures 2 ms at 2400 MHz / 40 MHz SR; saves raw IQ to `mensaje_ofdm_recibido.npy`; uses compat hack for enum constants. |
| `segundo_intento-TX.py` | OFDM / TX | OFDM-DBPSK transmitter: encodes a text message in DBPSK subcarriers at 2400 MHz / 1 MHz SR (USB 2.0 mode); designed for low-bandwidth links. |
| `test_notebook.py` | OFDM / full-duplex / channel-estimation | Most complete channel-sounding script: generates OFDM pilot, transmits and receives simultaneously at 1 GHz / 40 MHz SR using thread sync, saves to `estimacion_medio_ofdm.npy`. **Primary reference for `acquisition/full_duplex_capture.py`.** |

---

## Known-Good Hardware Parameters Summary

Extracted from the scripts above. Use these as ground truth when building `hardware/bladerf_device.py`.

| Parameter | Value | Source |
|-----------|-------|--------|
| Sample rate (stable) | 40 MHz | all sweep scripts |
| Sample rate (USB 2.0) | 1 MHz | `segundo_intento-TX.py` |
| Bandwidth | = sample rate | all scripts |
| TX gain (safe start) | 30–40 dB | sweep + FD scripts |
| TX gain (minimal) | 0 dB | `informacion.py` |
| RX gain | 40–60 dB | all RX scripts |
| Buffer format | SC16_Q11 | all scripts |
| Buffers / buffer_size / transfers | 16 / 8192 / 8 | all scripts |
| Stream timeout | 3500 ms | all scripts |
| Samples per step (1 ms) | 40 000 | all sweep scripts |
| DAC scale | ±2048 | all scripts |
| IQ normalization on RX | ÷ 2048.0 | all scripts |
| FD thread sync pattern | `threading.Event` (TX waits, RX fires) | `test_txrx_blog.py`, `test_notebook.py` |
| OFDM: FFT size / BW / guard / DC null | 1024 / 60 MHz / 100 bins / bin N//2 | `generador_simbolo_maestro.py` |
| OFDM pilot seed | 42 | `generador_simbolo_maestro.py` |
