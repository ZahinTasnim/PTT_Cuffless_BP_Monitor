"""
validate_on_ptt_dataset.py -- validate PTT_MONITOR_V2 on real recordings.

Pipeline (all steps use the real firmware source, compiled for a PC by harness/firmware_host_test.cpp):
  1. R-peak detection: firmware R-peaks vs the dataset's manually verified R-peak annotations.
  2. PTT: the firmware's own R-to-pulse timing, and how far it deviates from a reference PTT computed with the
     annotated R-peaks and the same pulse events.
  3. Blood pressure: change in PTT between rest and activity vs the change in cuff blood pressure
     (leave-one-subject-out; one rest reading per person is the only calibration).
Usage:  python validate_on_ptt_dataset.py <data_dir> <work_dir> [out_dir]
"""
import sys, os, glob, json, subprocess
import numpy as np, pandas as pd

FS = 500                      # recording tick rate (Hz); the firmware samples every other tick (250 Hz)
MS = 1000.0 / FS              # ms per tick
T0_MS = 5000                  # the harness starts its simulated clock at 5 s
WARMUP_TICKS = int(2.0 * FS)  # the firmware reports no beats during its 2 s noise-learning period
TOL_TICKS = int(0.100 * FS)   # a detection within +-100 ms of an annotation counts as a match
HERE = os.path.dirname(os.path.abspath(__file__))


def build_harness(out="fw_test"):
    h = os.path.join(HERE, "harness")
    src = os.path.join(HERE, "..", "firmware", "v2_revised", "PTT_MONITOR_V2")
    cmd = ["g++", "-std=gnu++17", "-O2", "-Wno-unused", "-Wno-format-truncation", f"-I{h}/stubs", f"-I{src}",
           f"{h}/firmware_host_test.cpp", "-o", out]
    subprocess.run(cmd, check=True)
    return out


def run_firmware(exe, work, rec):
    out = subprocess.run([exe, f"{work}/{rec}.ecg", f"{work}/{rec}.pulse"], capture_output=True, text=True, check=True).stdout
    r, rows = [], []
    for line in out.splitlines():
        if line.startswith("R,"):
            r.append(int(line[2:]))
        elif line and line[0].isdigit():
            f = line.split(",")
            rows.append(dict(ms=int(f[0]), ecg_bpm=int(f[1]), ptt=float(f[4]), ptt_shown=float(f[5])))
    return np.array(r), pd.DataFrame(rows)


def match(det, ann, tol):
    """One-to-one matching of detections to annotations within +-tol ticks (spacing >> tol, so nearest is unique)."""
    det = np.sort(det)
    j = np.searchsorted(det, ann)
    pairs = []
    for a, jj in zip(ann, j):
        c = [k for k in (jj - 1, jj) if 0 <= k < len(det) and abs(det[k] - a) <= tol]
        if c:
            k = min(c, key=lambda k: abs(det[k] - a)); pairs.append((a, det[k]))
    return np.array(pairs)


def reference_ptt(ann, pulse):
    """PTT from the annotated R-peaks and the same pulse events: latest R before each pulse, 80-700 ms."""
    out = {}
    j = np.searchsorted(ann, pulse) - 1
    for p, jj in zip(pulse, j):
        if jj >= 0:
            d = (p - ann[jj]) * MS
            if 80 <= d <= 700:
                out[p] = d
    return out


def main(data_dir, work, out_dir=None):
    out_dir = out_dir or os.path.join(HERE, "results")
    os.makedirs(out_dir, exist_ok=True)
    exe = build_harness(os.path.join(work, "fw_test"))
    info = pd.read_csv(os.path.join(HERE, "data", "subjects_info.csv")).set_index("record")
    recs = sorted({os.path.basename(f).split(".")[0] for f in glob.glob(f"{work}/*.ecg")},
                  key=lambda s: (int(s[1:].split("_")[0]), s))
    rows, jit_all, det_cache = [], [], {}
    for rec in recs:
        ann = np.loadtxt(f"{work}/{rec}.rpeaks", dtype=int)
        pulse = np.loadtxt(f"{work}/{rec}.pulse", dtype=int)
        n_ticks = len(np.loadtxt(f"{work}/{rec}.ecg", dtype=int))
        det, ptt = run_firmware(exe, work, rec)
        det_cache[rec] = (det, ptt)
        a_eval = ann[ann >= WARMUP_TICKS]
        pairs = match(det, a_eval, TOL_TICKS)
        tp = len(pairs)
        d_eval = det[det >= WARMUP_TICKS]
        offs = (pairs[:, 1] - pairs[:, 0]) * MS if tp else np.array([])
        # firmware PTT vs reference PTT for the same pulse events
        # what the displayed value would have been with the earlier 8-beat MEAN (same readings, same window)
        v = ptt.ptt.values
        mean8 = np.array([v[max(0, i - 7):i + 1].mean() for i in range(len(v))])
        med8 = np.array([np.median(v[max(0, i - 7):i + 1]) for i in range(len(v))])
        assert np.max(np.abs(med8 - ptt.ptt_shown.values)) < 0.06, "offline median does not match the firmware output"
        ptt = ptt.assign(pulse_tick=((ptt.ms - T0_MS) / 2).round().astype(int))
        ref = reference_ptt(ann, pulse)
        ptt["ref"] = ptt.pulse_tick.map(ref)
        both = ptt.dropna(subset=["ref"])
        jit = (both.ptt - both.ref).values
        jit_all.append(jit)
        subj, act = rec.split("_")
        hr_fw = 60000 / np.median(np.diff(d_eval) * MS) if len(d_eval) > 3 else np.nan
        hr_ann = 60000 / np.median(np.diff(a_eval) * MS)
        rows.append(dict(
            record=rec, subject=subj, activity=act, minutes=round(n_ticks / FS / 60, 1),
            annotated=len(a_eval), detected=len(d_eval), matched=tp,
            sensitivity=100 * tp / len(a_eval), ppv=100 * tp / max(len(d_eval), 1),
            timing_offset_median_ms=np.median(offs) if tp else np.nan, timing_offset_sd_ms=np.std(offs) if tp else np.nan,
            hr_firmware=hr_fw, hr_annotated=hr_ann,
            ptt_readings=len(ptt), ptt_median_ms=ptt.ptt.median(), ptt_iqr_ms=np.subtract(*np.percentile(ptt.ptt, [75, 25])),
            displayed_iqr_ms=np.subtract(*np.percentile(ptt.ptt_shown, [75, 25])),
            displayed_iqr_mean8_ms=np.subtract(*np.percentile(mean8, [75, 25])),
            ptt_vs_ref_bias_ms=np.mean(jit) if len(jit) else np.nan, ptt_vs_ref_sd_ms=np.std(jit) if len(jit) else np.nan,
            sbp_start=info.loc[rec, "bp_sys_start"], sbp_end=info.loc[rec, "bp_sys_end"],
            dbp_start=info.loc[rec, "bp_dia_start"], dbp_end=info.loc[rec, "bp_dia_end"],
            sbp=(info.loc[rec, "bp_sys_start"] + info.loc[rec, "bp_sys_end"]) / 2,
            dbp=(info.loc[rec, "bp_dia_start"] + info.loc[rec, "bp_dia_end"]) / 2,
            hr_cuff=(info.loc[rec, "hr_1_start"] + info.loc[rec, "hr_1_end"]) / 2))
    df = pd.DataFrame(rows)
    df.to_csv(os.path.join(out_dir, "per_recording.csv"), index=False, float_format="%.2f")

    # ---- summary of detection and timing
    tot = df[["annotated", "detected", "matched"]].sum()
    summary = dict(
        n_recordings=len(df), n_subjects=df.subject.nunique(),
        annotated_beats=int(tot.annotated), detected_beats=int(tot.detected), matched_beats=int(tot.matched),
        sensitivity_pct=100 * tot.matched / tot.annotated, ppv_pct=100 * tot.matched / tot.detected,
        median_sensitivity_pct=df.sensitivity.median(), min_sensitivity_pct=df.sensitivity.min(),
        min_sensitivity_record=df.loc[df.sensitivity.idxmin(), "record"],
        timing_offset_median_ms=df.timing_offset_median_ms.median(), timing_offset_sd_ms=df.timing_offset_sd_ms.median(),
        hr_abs_err_bpm_median=float((df.hr_firmware - df.hr_annotated).abs().median()),
        hr_abs_err_bpm_max=float((df.hr_firmware - df.hr_annotated).abs().max()),
        ptt_readings=int(df.ptt_readings.sum()),
        ptt_vs_ref_bias_ms=float(np.nanmean(df.ptt_vs_ref_bias_ms)), ptt_vs_ref_sd_ms=float(np.nanmedian(df.ptt_vs_ref_sd_ms)))

    # ---- blood pressure: change from rest, leave-one-subject-out
    def loso(frame, tgt):
        """Calibration = one resting reading per person. A population slope (learned from the OTHER subjects)
        turns the change in PTT (or heart rate) from rest into a predicted change in blood pressure."""
        sit = frame[frame.activity == "sit"].set_index("subject")
        d = frame[frame.activity != "sit"].copy()
        for col in ("ptt_median_ms", tgt, "hr_firmware"):
            d["d_" + col] = d[col] - d.subject.map(sit[col])
        d = d.reset_index(drop=True)
        res = {"model": [], "zero": [], "hr": []}; preds = []
        for sj in sorted(d.subject.unique(), key=lambda x: int(x[1:])):
            tr, te = d[d.subject != sj], d[d.subject == sj]
            b_ptt = (tr.d_ptt_median_ms * tr["d_" + tgt]).sum() / (tr.d_ptt_median_ms ** 2).sum()
            b_hr = (tr.d_hr_firmware * tr["d_" + tgt]).sum() / (tr.d_hr_firmware ** 2).sum()
            for _, r in te.iterrows():
                p, ph = b_ptt * r.d_ptt_median_ms, b_hr * r.d_hr_firmware
                preds.append(dict(record=r.record, measured=r["d_" + tgt], predicted_ptt=p, predicted_hr=ph))
                res["model"].append(abs(p - r["d_" + tgt])); res["zero"].append(abs(r["d_" + tgt])); res["hr"].append(abs(ph - r["d_" + tgt]))
        out = dict(n=len(res["model"]), mae_ptt=float(np.mean(res["model"])), mae_no_change=float(np.mean(res["zero"])),
                   mae_hr=float(np.mean(res["hr"])),
                   r_ptt=float(np.corrcoef(d.d_ptt_median_ms, d["d_" + tgt])[0, 1]),
                   r_hr=float(np.corrcoef(d.d_hr_firmware, d["d_" + tgt])[0, 1]))
        return d, out, preds

    d, bp, preds = None, {}, {}
    for tgt in ("sbp", "dbp"):
        d_t, bp[tgt], preds[tgt] = loso(df, tgt)
        if d is None:
            d = d_t
        else:
            d["d_" + tgt] = d_t["d_" + tgt]
    # the reference choice (mean of the start/end cuff readings) was fixed before looking at results;
    # this repeats the analysis with only the start or only the end reading as a robustness check
    robust = {}
    for which in ("start", "end"):
        fr = df.copy(); fr["sbp"] = fr["sbp_" + which]; fr["dbp"] = fr["dbp_" + which]
        robust[which] = {t: loso(fr, t)[1] for t in ("sbp", "dbp")}
    sit_rows = df[df.activity == "sit"]
    drift = (sit_rows.sbp_end - sit_rows.sbp_start)
    summary["bp"] = bp
    summary["bp_reference_robustness"] = robust
    summary["cuff_rest_sbp_change_start_to_end"] = dict(values=[float(x) for x in drift], mean_abs=float(drift.abs().mean()),
                                                       min_abs=float(drift.abs().min()), max_abs=float(drift.abs().max()))
    summary["mean_abs_sbp_change_walk_run"] = float(d.d_sbp.abs().mean())
    summary["ptt_by_activity_ms"] = {k: float(v) for k, v in df.groupby("activity").ptt_median_ms.mean().items()}
    summary["ptt_shorter_than_rest"] = f"{int((d.d_ptt_median_ms < 0).sum())} of {len(d)}"
    summary["sbp_higher_than_rest"] = f"{int((d.d_sbp > 0).sum())} of {len(d)}"
    summary["r_dPTT_dHR"] = float(np.corrcoef(d.d_ptt_median_ms, d.d_hr_firmware)[0, 1])
    summary["displayed_value_spread_ms_median"] = float(df.displayed_iqr_ms.median())
    json.dump(summary, open(os.path.join(out_dir, "summary.json"), "w"), indent=1)
    d.to_csv(os.path.join(out_dir, "changes_from_rest.csv"), index=False, float_format="%.2f")
    pd.DataFrame(preds["sbp"]).to_csv(os.path.join(out_dir, "loso_predictions_sbp.csv"), index=False, float_format="%.2f")
    pd.DataFrame(preds["dbp"]).to_csv(os.path.join(out_dir, "loso_predictions_dbp.csv"), index=False, float_format="%.2f")
    return df, d, summary, bp, det_cache


if __name__ == "__main__":
    df, d, summary, bp, _ = main(sys.argv[1], sys.argv[2], sys.argv[3] if len(sys.argv) > 3 else None)
    pd.set_option("display.width", 250); pd.set_option("display.max_columns", 30)
    print(df[["record", "annotated", "detected", "matched", "sensitivity", "ppv", "timing_offset_median_ms",
              "timing_offset_sd_ms", "hr_firmware", "hr_annotated", "ptt_readings", "ptt_median_ms", "ptt_iqr_ms",
              "ptt_vs_ref_bias_ms", "ptt_vs_ref_sd_ms"]].round(1).to_string(index=False))
    print(json.dumps(summary, indent=1))
