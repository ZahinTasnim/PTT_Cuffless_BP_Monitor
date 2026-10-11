"""
prepare_inputs.py -- prepare the real recordings for the firmware test.

For every recording in <data_dir> (500 Hz CSVs from the PhysioNet Pulse Transit Time PPG Dataset):
  * ECG is reduced from the dataset's 16-bit range to the ESP32's 12-bit ADC range (>> 4),
    so the firmware sees realistic quantisation.
  * The fingertip PPG is turned into 'pulse detected' events (band-pass 0.75-5 Hz, systolic peak picking).
    These events replace the MAX30100 library's beat callback, which cannot run on recorded data.
  * Polarity is chosen from the waveform shape (a blood-volume pulse rises faster than it falls); the red/infrared
    channel is chosen by how many ANNOTATED R-peaks (manually verified labels) are followed by a pulse event.
    Both choices are made once for all recordings. The dataset page labels red/infrared inconsistently, so the
    choice comes from the data, not the labels.
Writes work/<record>.ecg (one 12-bit sample per line, 500 Hz) and work/<record>.pulse (event sample indices).
"""
import sys, os, glob, json
import numpy as np, pandas as pd
from scipy.signal import butter, sosfiltfilt, find_peaks

FS = 500
SOS = butter(2, [0.75, 5.0], btype="band", fs=FS, output="sos")
# Fingertip (distal phalanx) sensor, red and infrared only: the MAX30100 has no green LED, so the green channel
# (pleth_3), which scores slightly higher, is deliberately excluded.
DISTAL = ["pleth_1", "pleth_2"]


def ppg_events(x, sign):
    """Systolic peaks of the band-passed PPG (sign=+1 or -1 flips polarity)."""
    f = sign * sosfiltfilt(SOS, x.astype(float))
    pk, props = find_peaks(f, distance=int(0.3 * FS), prominence=1e-9)
    if len(pk) == 0:
        return pk
    prom = props["prominences"]
    # keep a peak if it is at least 30% of the median prominence of the pulses within +-10 s around it
    # (an adaptive threshold, like the real library's; a single global threshold dropped weak stretches)
    t = pk / FS
    lo, hi = np.searchsorted(t, t - 10), np.searchsorted(t, t + 10)
    keep = np.array([prom[i] >= 0.3 * np.median(prom[lo[i]:hi[i]]) for i in range(len(pk))])
    return pk[keep]


def pairing(r_idx, p_idx):
    """For each R-peak, delay (ms) to the next PPG event within 100-600 ms; NaN if none."""
    out = np.full(len(r_idx), np.nan)
    j = np.searchsorted(p_idx, r_idx + int(0.1 * FS))
    for k, jj in enumerate(j):
        if jj < len(p_idx) and p_idx[jj] - r_idx[k] <= int(0.6 * FS):
            out[k] = (p_idx[jj] - r_idx[k]) * 1000 / FS
    return out


def main(data_dir, out_dir="work"):
    os.makedirs(out_dir, exist_ok=True)
    files = sorted(glob.glob(os.path.join(data_dir, "s*_*.csv")))
    files = [f for f in files if not os.path.basename(f).split(".")[0].endswith("_1")] or files
    recs = {}
    for f in files:
        name = os.path.basename(f).replace("_1.csv", "").replace(".csv", "")
        d = pd.read_csv(f, usecols=["ecg", "peaks"] + DISTAL)
        recs[name] = d
    print(len(recs), "recordings:", ", ".join(sorted(recs)))

    # 1) polarity from waveform shape, independent of any timing: a blood-volume pulse rises faster than it
    #    falls, so its derivative is positively skewed. Raw reflective-PPG counts usually go DOWN with blood volume.
    from scipy.stats import skew
    sign_of = {}
    for ch in DISTAL:
        sk = [skew(np.diff(sosfiltfilt(SOS, d[ch].values.astype(float)))) for d in recs.values()]
        sign_of[ch] = +1 if np.median(sk) > 0 else -1
        print(f"  {ch}: derivative skewness median {np.median(sk):+.2f} "
              f"(positive in {sum(x > 0 for x in sk)}/{len(sk)} recordings) -> polarity {sign_of[ch]:+d}")

    # 2) channel (red vs infrared) by how many annotated R-peaks are followed by a PPG event 100-600 ms later
    score = {}
    for ch in DISTAL:
        frac, iqr, med = [], [], []
        for name, d in recs.items():
            r = np.where(d["peaks"].values > 0)[0]
            delay = pairing(r, ppg_events(d[ch].values, sign_of[ch]))
            v = delay[~np.isnan(delay)]
            frac.append(np.mean(~np.isnan(delay)))
            iqr.append(np.subtract(*np.percentile(v, [75, 25])) if len(v) > 10 else np.inf)
            med.append(np.median(v) if len(v) > 10 else np.nan)
        score[(ch, sign_of[ch])] = (float(np.mean(frac)), float(np.median(iqr)))
        print(f"  {ch} polarity {sign_of[ch]:+d}: R-peaks followed by a pulse {100*np.mean(frac):5.1f}% | "
              f"median R-to-pulse delay {np.nanmedian(med):5.1f} ms | spread (IQR) {np.median(iqr):5.1f} ms")
    best = max(score, key=lambda k: score[k][0])
    print("chosen:", best)

    ch, sign = best
    for name, d in recs.items():
        np.savetxt(f"{out_dir}/{name}.ecg", (d["ecg"].values.astype(np.int64) >> 4), fmt="%d")
        np.savetxt(f"{out_dir}/{name}.pulse", ppg_events(d[ch].values, sign), fmt="%d")
        np.savetxt(f"{out_dir}/{name}.rpeaks", np.where(d["peaks"].values > 0)[0], fmt="%d")
    json.dump(dict(channel=ch, sign=sign, scores={f"{k[0]}{k[1]:+d}": v for k, v in score.items()}),
              open(f"{out_dir}/ppg_choice.json", "w"), indent=1)


if __name__ == "__main__":
    main(sys.argv[1] if len(sys.argv) > 1 else "data_dir", sys.argv[2] if len(sys.argv) > 2 else "work")
