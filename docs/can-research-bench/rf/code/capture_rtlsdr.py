#!/usr/bin/env python3
"""
capture_rtlsdr.py — التقاط IQ خام (استقبال فقط) من RTL-SDR حول 433.92 MHz.

⚖️ استقبال فقط. لا إرسال. للاستخدام على مفتاحك الخاص لأغراض التحليل والتعلّم.
    RTL-SDR لا يرسل أصلًا. إن استخدمت جهازًا يرسل (HackRF)، لا تفعّل الإرسال.

يحفظ العيّنات بصيغة complex64 موحّدة (I/Q normalized إلى ~[-1, 1]) ليقرأها
ook_decode.py و plot_timing.py مباشرة.

مثال:
    python capture_rtlsdr.py --freq 433.92e6 --rate 2.048e6 --seconds 3 --out signal.iq
"""
import argparse
import sys
import numpy as np


def capture(freq_hz, rate_hz, seconds, gain, ppm):
    """يلتقط تدفّق IQ من RTL-SDR ويعيده كـ np.complex64."""
    try:
        from rtlsdr import RtlSdr
    except ImportError:
        sys.exit("pyrtlsdr غير مثبّتة. ثبّت: pip install pyrtlsdr  (ويلزم مشغّل librtlsdr)")

    sdr = RtlSdr()
    try:
        sdr.sample_rate = float(rate_hz)
        sdr.center_freq = float(freq_hz)
        sdr.freq_correction = int(ppm)          # تصحيح انحراف البلّورة (ppm)
        sdr.gain = 'auto' if gain is None else float(gain)

        n_samples = int(rate_hz * seconds)
        # read_samples يعيد complex128 منظّمة أصلًا حول 0
        print(f"[*] التقاط {seconds}s @ {freq_hz/1e6:.3f} MHz، rate={rate_hz/1e6:.3f} Msps ...")
        print("[*] اضغط زر المفتاح الآن.")
        iq = sdr.read_samples(n_samples)
        return iq.astype(np.complex64)
    finally:
        sdr.close()


def main():
    ap = argparse.ArgumentParser(description="التقاط IQ خام من RTL-SDR (استقبال فقط)")
    ap.add_argument("--freq", type=float, default=433.92e6, help="التردد المركزي بالهرتز")
    ap.add_argument("--rate", type=float, default=2.048e6, help="معدّل العيّنات (Msps)")
    ap.add_argument("--seconds", type=float, default=3.0, help="مدّة الالتقاط بالثواني")
    ap.add_argument("--gain", type=float, default=None, help="الكسب (dB) أو auto إن تُرك")
    ap.add_argument("--ppm", type=int, default=0, help="تصحيح انحراف التردد (ppm)")
    ap.add_argument("--out", default="signal.iq", help="ملف الإخراج (complex64)")
    args = ap.parse_args()

    iq = capture(args.freq, args.rate, args.seconds, args.gain, args.ppm)
    iq.tofile(args.out)
    print(f"[+] حُفظ {iq.size} عيّنة ({iq.nbytes/1e6:.1f} MB) في {args.out}")
    print(f"[i] لفكّ التضمين: python ook_decode.py {args.out} --rate {args.rate:g} --report")


if __name__ == "__main__":
    main()
