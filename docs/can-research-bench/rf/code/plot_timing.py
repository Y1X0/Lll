#!/usr/bin/env python3
"""
plot_timing.py — مخطط زمني لإشارة OOK/ASK جاهز لتقرير مشروع التخرّج.

يرسم ثلاث لوحات:
  1. مغلّف المقدار مع العتبة التكيّفية
  2. الإشارة الثنائية الناتجة (النبضات)
  3. مدرّج أطوال النبضات (لإظهار زمن الرمز)

⚖️ تصوّر تحليلي لإشارة مملوكة، استقبال فقط. دليل على تحليل الإشارة برمجيًا
    دون أدوات جاهزة — وهو بالضبط ما يطلبه التقرير الأكاديمي.

مثال:
    python plot_timing.py signal.iq --rate 2.048e6 --out timing.png --zoom 0 0.05
"""
import argparse
import numpy as np
import matplotlib.pyplot as plt

from ook_decode import load_iq, envelope, adaptive_threshold, binarize, run_lengths


def main():
    ap = argparse.ArgumentParser(description="مخطط زمني لإشارة OOK للتقرير")
    ap.add_argument("iqfile")
    ap.add_argument("--rate", type=float, required=True)
    ap.add_argument("--fmt", default="auto")
    ap.add_argument("--decim", type=int, default=4, help="تقليل للعرض (افتراضي 4)")
    ap.add_argument("--zoom", type=float, nargs=2, default=None,
                    metavar=("T0", "T1"), help="نطاق زمني بالثواني للتكبير")
    ap.add_argument("--out", default="timing.png")
    args = ap.parse_args()

    iq = load_iq(args.iqfile, args.fmt)
    mag, fs = envelope(iq, args.rate, decim=args.decim)
    thr = adaptive_threshold(mag)
    binary = binarize(mag, thr) if thr is not None else np.zeros_like(mag, dtype=np.int8)
    runs = run_lengths(binary)

    t = np.arange(mag.size) / fs
    if args.zoom:
        m = (t >= args.zoom[0]) & (t <= args.zoom[1])
    else:
        # تكبير تلقائي حول أول نشاط
        active = np.flatnonzero(binary)
        if active.size:
            c = active[active.size // 2]
            w = int(fs * 0.02)                    # نافذة 20ms
            m = np.zeros_like(binary, dtype=bool)
            m[max(0, c - w):c + w] = True
        else:
            m = np.ones_like(binary, dtype=bool)

    pulse_us = np.array([ln / fs * 1e6 for _, ln in runs if ln > 2])

    fig, ax = plt.subplots(3, 1, figsize=(11, 8), constrained_layout=True)

    ax[0].plot(t[m] * 1e3, mag[m], lw=0.7, color="#2563eb")
    if thr is not None:
        ax[0].axhline(thr, color="#dc2626", ls="--", lw=1, label=f"عتبة تكيّفية = {thr:.3f}")
        ax[0].legend(loc="upper right")
    ax[0].set_title("Amplitude Envelope — مغلّف المقدار")
    ax[0].set_ylabel("Amplitude")
    ax[0].grid(alpha=0.3)

    ax[1].plot(t[m] * 1e3, binary[m], lw=0.8, color="#059669", drawstyle="steps-post")
    ax[1].set_title("Demodulated Binary (OOK) — الإشارة الثنائية")
    ax[1].set_ylabel("Bit level")
    ax[1].set_xlabel("Time (ms)")
    ax[1].set_ylim(-0.2, 1.2)
    ax[1].grid(alpha=0.3)

    if pulse_us.size:
        ax[2].hist(pulse_us, bins=60, color="#7c3aed", alpha=0.8)
        ax[2].set_title("Pulse-Width Histogram — توزيع أطوال النبضات (يكشف زمن الرمز)")
        ax[2].set_xlabel("Pulse width (µs)")
        ax[2].set_ylabel("Count")
        ax[2].grid(alpha=0.3)

    fig.suptitle("OOK/ASK Key-Fob Signal Analysis @ 433.92 MHz", fontsize=13, weight="bold")
    fig.savefig(args.out, dpi=150)
    print(f"[+] حُفظ المخطط في {args.out}")
    print(f"[i] النبضات: {len(runs)} | متوسط الطول: "
          f"{pulse_us.mean():.1f} µs" if pulse_us.size else "[i] لا نبضات معتبرة")


if __name__ == "__main__":
    main()
