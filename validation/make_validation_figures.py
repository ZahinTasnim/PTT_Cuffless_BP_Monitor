"""Figures for the validation: python make_validation_figures.py <data_dir> <work_dir>"""
import sys, os, json
import numpy as np, pandas as pd
import matplotlib; matplotlib.use("Agg")
import matplotlib.pyplot as plt
from scipy.signal import butter, sosfiltfilt
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from validate_on_ptt_dataset import run_firmware, FS, MS

HERE = os.path.dirname(os.path.abspath(__file__))
RES, FIG = os.path.join(HERE, "results"), os.path.join(HERE, "figures")
plt.rcParams.update({"font.size": 8.5, "axes.titlesize": 9.5, "figure.dpi": 200, "axes.spines.top": False, "axes.spines.right": False})
BLUE, RED, GREY, GREEN = "#1B4F8A", "#C0392B", "#8C8C8C", "#2E6F4E"


def traces(data_dir, work):
    ch = json.load(open(f"{work}/ppg_choice.json"))
    d = pd.read_csv(f"{data_dir}/s10_sit_1.csv" if os.path.exists(f"{data_dir}/s10_sit_1.csv") else f"{data_dir}/s10_sit.csv",
                    usecols=["ecg", "peaks", ch["channel"]])
    det, _ = run_firmware(os.path.join(work, "fw_test"), work, "s10_sit")
    pulse = np.loadtxt(f"{work}/s10_sit.pulse", dtype=int)
    sos = butter(2, [0.75, 5.0], btype="band", fs=FS, output="sos")
    ppg = ch["sign"] * sosfiltfilt(sos, d[ch["channel"]].values.astype(float))
    ecg = d["ecg"].values >> 4
    ann = np.where(d["peaks"].values > 0)[0]
    a, b = 20000, 26000
    t = np.arange(a, b) / FS
    fig, ax = plt.subplots(2, 1, figsize=(7.2, 3.9), sharex=True, gridspec_kw=dict(hspace=0.12))
    ax[0].plot(t, ecg[a:b], color="#222", lw=0.8)
    m = (ann >= a) & (ann < b); ax[0].plot(ann[m] / FS, ecg[ann[m]] + 40, "v", color=GREY, ms=4, label="annotated R-peak (dataset)")
    m = (det >= a) & (det < b); ax[0].plot(det[m] / FS, np.full(m.sum(), ecg[a:b].min() - 25), "|", color=RED, ms=9, mew=1.6,
                                           label="detected by the firmware")
    ax[0].set_ylim(ecg[a:b].min() - 90, ecg[a:b].max() * 1.32)
    ax[0].set_ylabel("ECG (12-bit counts)"); ax[0].legend(loc="upper right", fontsize=7, ncol=2, frameon=False)
    ax[0].set_title("Real recording s10_sit (seated), processed by the version 2 firmware code")
    ax[1].plot(t, ppg[a:b], color=BLUE, lw=0.9)
    m = (pulse >= a) & (pulse < b); ax[1].plot(pulse[m] / FS, ppg[pulse[m]], "o", color=BLUE, ms=3.5, label="pulse event (stands in for the MAX30100 beat callback)")
    y0 = ppg[a:b].min() * 1.15
    for dk in det[(det >= a) & (det < b)]:
        nxt = pulse[(pulse > dk) & ((pulse - dk) * MS <= 700) & ((pulse - dk) * MS >= 80)]
        if len(nxt):
            ax[1].plot([dk / FS, nxt[0] / FS], [y0, y0], color=GREEN, lw=2.2, marker="|", ms=7, solid_capstyle="butt")
            ax[1].text((dk + nxt[0]) / 2 / FS, y0 * 1.06, f"{(nxt[0]-dk)*MS:.0f}", ha="center", va="top", color=GREEN, fontsize=6.5)
    ax[1].set_ylabel("fingertip PPG (filtered)"); ax[1].set_xlabel("time (s)"); ax[1].set_ylim(y0 * 1.25, ppg[a:b].max() * 1.55)
    ax[1].plot([], [], color=GREEN, lw=2.2, label="firmware PTT in ms (R-peak to next pulse)")
    ax[1].legend(loc="upper right", fontsize=7, frameon=False)
    fig.savefig(f"{FIG}/fig1_firmware_on_real_recording.png", bbox_inches="tight"); plt.close()


def summary():
    pr = pd.read_csv(f"{RES}/per_recording.csv"); ch = pd.read_csv(f"{RES}/changes_from_rest.csv")
    sj = json.load(open(f"{RES}/summary.json"))
    fig, ax = plt.subplots(2, 2, figsize=(7.4, 6.0)); fig.subplots_adjust(hspace=0.42, wspace=0.28)
    # a) detection
    x = np.arange(len(pr)); w = 0.38
    ax[0, 0].bar(x - w / 2, pr.sensitivity, w, color=BLUE, label="sensitivity"); ax[0, 0].bar(x + w / 2, pr.ppv, w, color=RED, label="precision")
    ax[0, 0].set_ylim(80, 106); ax[0, 0].set_xticks(x); ax[0, 0].set_xticklabels(pr.record, rotation=60, ha="right", fontsize=7)
    ax[0, 0].set_ylabel("%"); ax[0, 0].legend(fontsize=7, frameon=False, loc="upper center", ncol=2)
    ax[0, 0].set_title(f"(a) Beat detection: {sj['sensitivity_pct']:.1f}% / {sj['ppv_pct']:.1f}%", fontsize=9)
    # b) PTT by activity
    order = ["sit", "walk", "run"]; xs = {a: i for i, a in enumerate(order)}
    for s, g in pr.groupby("subject"):
        g = g.sort_values("activity", key=lambda c: c.map(xs))
        ax[0, 1].errorbar([xs[a] for a in g.activity], g.ptt_median_ms, yerr=g.ptt_iqr_ms / 2, marker="o", ms=4, lw=1, capsize=2, label=s, alpha=0.9)
    ax[0, 1].set_xticks(range(3)); ax[0, 1].set_xticklabels(order); ax[0, 1].set_ylabel("median PTT (ms), bars = IQR")
    ax[0, 1].legend(fontsize=7, frameon=False, ncol=2); ax[0, 1].set_title("(b) PTT vs rest: shorter in 8 of 8", fontsize=9)
    # c, d) change in SBP vs change in PTT / HR
    mk = {"walk": "^", "run": "s"}
    for k, (col, xl, r, panel) in enumerate([("d_ptt_median_ms", "change in PTT from rest (ms)", sj["bp"]["sbp"]["r_ptt"], "(c) PTT vs SBP"),
                                              ("d_hr_firmware", "change in heart rate from rest (bpm)", sj["bp"]["sbp"]["r_hr"], "(d) heart rate vs SBP")]):
        a = ax[1, k]
        for act, g in ch.groupby("activity"):
            a.scatter(g[col], g.d_sbp, marker=mk[act], s=36, color=BLUE if act == "walk" else RED, label=act, zorder=3)
        for _, rr in ch.iterrows():
            a.annotate(rr.subject, (rr[col], rr.d_sbp), xytext=(3, 3), textcoords="offset points", fontsize=6.5, color="#444")
        a.axhline(0, color=GREY, lw=0.6); a.axvline(0, color=GREY, lw=0.6)
        a.set_xlabel(xl); a.set_ylabel("change in cuff SBP from rest (mmHg)"); a.legend(fontsize=7, frameon=False)
        a.set_title(f"{panel}: r = {r:+.2f} (n = 8)", fontsize=9)
    fig.savefig(f"{FIG}/fig2_validation_summary.png", bbox_inches="tight"); plt.close()


if __name__ == "__main__":
    os.makedirs(FIG, exist_ok=True)
    traces(sys.argv[1], sys.argv[2]); summary(); print("figures written")
