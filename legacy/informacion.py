from bladerf import _bladerf
import numpy as np

sdr = _bladerf.BladeRF()
tx_ch = sdr.Channel(_bladerf.CHANNEL_TX(0)) # give it a 0 or 1

sample_rate = 10e6
center_freq = 100e6
gain = 0 # -15 to 60 dB. for transmitting, start low and slowly increase, and make sure antenna is connected
num_samples = int(1e6)
repeat = 30 # number of times to repeat our signal
print('duration of transmission:', num_samples/sample_rate*repeat, 'seconds')

# Generate IQ samples to transmit (in this case, a simple tone)
t = np.arange(num_samples) / sample_rate
f_tone = 1e6
samples = np.exp(1j * 2 * np.pi * f_tone * t) # will be -1 to +1
samples = samples.astype(np.complex64)
samples *= 2048.0 # Scale to -1 to 1 (it is using a 12-bit DAC)
samples = samples.view(np.int16)
buf = samples.tobytes() # convert our samples to bytes and use them as transmit buffer

tx_ch.frequency = center_freq
tx_ch.sample_rate = sample_rate
tx_ch.bandwidth = sample_rate/2
tx_ch.gain = gain

# Setup synchronous stream
sdr.sync_config(layout=_bladerf.ChannelLayout.TX_X1, # or TX_X2
                fmt=_bladerf.Format.SC16_Q11, # int16s
                num_buffers=16,
                buffer_size=8192,
                num_transfers=8,
                stream_timeout=3500)

print("Starting transmit!")
repeats_remaining = repeat - 1
tx_ch.enable = True
while True:
    sdr.sync_tx(buf, num_samples) # write to bladeRF
    print(repeats_remaining)
    if repeats_remaining > 0:
        repeats_remaining -= 1
    else:
        break

print("Stopping transmit")
tx_ch.enable = False