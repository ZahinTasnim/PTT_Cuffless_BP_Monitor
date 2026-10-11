"""
detector_simulation.py -- checks the ECG beat detection logic without hardware.

Builds a simulated 12-bit ECG (as the ESP32 reads it: 0-4095) with sharp R-waves,
broad T-waves, breathing drift and random noise, then runs two detectors that
mirror the firmware line by line:
  * original: FINAL_PROGRAM.ino (10-sample average, threshold = average + 10)
  * v2:       PTT_MONITOR_V2.ino (slope-based, adaptive to the noise level)
It also runs both on noise alone (electrodes off), where the correct answer is 0 beats.
Requires: numpy.   Run: python tests/detector_simulation.py
"""
import numpy as np

rng = np.random.default_rng(7)
FS, T = 250, 30
t = np.arange(0, T, 1 / FS)


def ecg(hr, amp, noise=25):
    s = np.full_like(t, 2048.0)
    for tb in np.arange(0.5, T, 60 / hr):
        s += amp * np.exp(-((t - tb) ** 2) / (2 * 0.008 ** 2))                        # QRS
        s += 0.35 * amp * np.exp(-((t - tb - 0.25) ** 2) / (2 * 0.04 ** 2))           # T-wave
    s += 40 * np.sin(2 * np.pi * 0.25 * t)                                             # breathing drift
    return np.clip(s + rng.normal(0, noise, t.size), 0, 4095).round()


def original(sig250):
    sig = sig250[::2][: T * 100]                    # original loop ran at ~100 Hz (delay(10))
    win = [512] * 10; avg = 512; det = 0; prev = 0; beats = []
    for i, raw in enumerate(sig):
        win[i % 10] = raw; f = sum(win) / 10
        avg = (avg * 9 + f) / 10; thr = avg + 10; ms = i * 10
        if f > thr and det == 0 and ms - prev > 300:
            det = 1; prev = ms; beats.append(ms)
        if f < thr:
            det = 0
    return beats


def v2(sig, K=6.0, warm_ms=2000):
    win = [sig[0]] * 5; wsum = sig[0] * 5; h = [sig[0]] * 3
    noise = peak = 1.0; above = False; last = -10**9; beats = []
    for i, raw in enumerate(sig):
        wsum += raw - win[i % 5]; win[i % 5] = raw; h = [h[1], h[2], wsum / 5]
        e = abs(h[2] - h[0]); peak = e if e > peak else peak + 0.002 * (noise - peak)
        thr = noise + 0.5 * (peak - noise); ms = i * 4
        if not above and ms >= warm_ms and e > thr and peak > K * noise and ms - last > 300:
            above = True; beats.append(ms); last = ms
        elif above and e < thr:
            above = False
        if not above:
            noise += 0.01 * (e - noise)
    return beats


def hr(beats):
    return 60000 / np.median(np.diff(beats)) if len(beats) > 3 else float("nan")


if __name__ == "__main__":
    print(f"{'signal':28s} {'original HR':>12s} {'v2 HR':>8s} {'v2 beats found':>15s}")
    for true_hr in (60, 72, 110):
        for amp in (600, 200):
            s = ecg(true_hr, amp)
            expected = int(np.sum(np.arange(0.5, T, 60 / true_hr) >= 2.0))
            b = v2(s)
            print(f"{true_hr:3d} bpm, R-wave {amp:3d} counts   {hr(original(s)):12.1f} {hr(b):8.1f} {len(b):8d} of {expected}")
    for sd in (25, 60):
        f = np.clip(2048 + 40 * np.sin(2 * np.pi * 0.25 * t) + rng.normal(0, sd, t.size), 0, 4095).round()
        print(f"electrodes off, noise sd {sd:2d}   false beats: original {len(original(f))}, v2 {len(v2(f))}")
