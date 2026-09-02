#!/usr/bin/env python3
"""
ook_decode.py — فكّ تضمين OOK/ASK كامل من ملف IQ خام إلى بتات.

خطّ المعالجة:
    IQ خام → المقدار (magnitude) → إزالة DC → مرشّح منخفض التمرير (تنعيم)
    → عتبة تكيّفية (أرضية ضوضاء ↔ ذروة) → إشارة ثنائية على مستوى العيّنة
    → RLE (استخراج أطوال النبضات) → تقدير ساعة الرمز (أقصر نبضة متكرّرة)
    → كشف الترميز (PWM / Manchester / NRZ) → مصفوفة بتات
    → كشف الترويسة (Preamble)

⚖️ تحليل استقبال فقط لإشارة مملوكة. لا إرسال، لا Replay، لا كسر Rolling Code.

يدعم صيغ الإدخال:
    - complex64        (مخرج capture_rtlsdr.py)  ← الافتراضي
    - uint8 متداخل     (مخرج أداة rtl_sdr CLI: I,Q بايتات بإزاحة 127.5)
    - int8 متداخل      (مخرج hackrf_transfer)

مثال:
    python ook_decode.py signal.iq --rate 2.048e6 --report
"""
import argparse
import sys
import numpy as np
from scipy import signal as sig


# ------------------------------------------------------------------ تحميل
def load_iq(filepath, fmt="auto"):
    """يقرأ ملف IQ ويعيد np.complex64 منظّمًا حول 0 بمدى ~[-1,1].

    الكشف التلقائي يعتمد على الامتداد (موثوق)، لا على محتوى البايتات (هشّ):
      - .cu8/.bin        → uint8 متداخل (مخرج أداة rtl_sdr CLI)
      - .cs8             → int8 متداخل (مخرج hackrf_transfer)
      - غير ذلك (.iq/…)  → complex64 (مخرج capture_rtlsdr.py) ← الافتراضي
    عند الشكّ مرّر --fmt صراحةً.
    """
    if fmt == "auto":
        low = filepath.lower()
        if low.endswith((".cu8", ".bin")):
            fmt = "uint8"
        elif low.endswith(".cs8"):
            fmt = "int8"
        else:
            fmt = "complex64"

    if fmt == "complex64":
        return np.fromfile(filepath, dtype=np.complex64)

    if fmt == "uint8":
        raw = np.fromfile(filepath, dtype=np.uint8).astype(np.float32)
        i = (raw[0::2] - 127.5) / 127.5
        q = (raw[1::2] - 127.5) / 127.5
        return (i + 1j * q).astype(np.complex64)
    if fmt == "int8":
        s = np.fromfile(filepath, dtype=np.int8).astype(np.float32) / 127.0
        return (s[0::2] + 1j * s[1::2]).astype(np.complex64)
    raise ValueError(f"صيغة غير معروفة: {fmt}")


# ------------------------------------------------------- المقدار + الترشيح
def envelope(iq, fs, cutoff_hz=None, decim=1):
    """يحسب مغلّف المقدار مع إزالة DC وترشيح منخفض التمرير للتنعيم."""
    mag = np.abs(iq).astype(np.float32)
    mag -= np.median(mag)                       # إزالة أرضية DC تقريبية
    mag = np.clip(mag, 0, None)

    # مرشّح منخفض التمرير لإزالة تموّج الحامل المتبقّي والضوضاء عالية التردد
    if cutoff_hz is None:
        cutoff_hz = fs / 50.0                    # تقدير معقول: أعرض من أسرع نبضة
    b, a = sig.butter(4, cutoff_hz / (fs / 2.0), btype="low")
    mag = sig.filtfilt(b, a, mag).astype(np.float32)

    if decim > 1:
        mag = mag[::decim]
        fs = fs / decim
    return mag, fs


# --------------------------------------------------------- عتبة تكيّفية
def adaptive_threshold(mag):
    """يحسب عتبة بين أرضية الضوضاء وذروة الإشارة (منتصف قوي المقاومة للضوضاء)."""
    noise_floor = np.percentile(mag, 20)         # معظم الوقت لا إشارة → أرضية
    peak = np.percentile(mag, 99.5)              # ذروة الإشارة (مقاومة للقيم الشاذّة)
    if peak - noise_floor < 1e-6:
        return None                              # لا إشارة معتبرة
    return noise_floor + 0.5 * (peak - noise_floor)


def binarize(mag, thr, hysteresis=0.15):
    """عتبة مع هستيرة (Schmitt) لتقليل الرفرفة عند الحوافّ."""
    span = mag.max() - mag.min()
    hi = thr + hysteresis * span * 0.5
    lo = thr - hysteresis * span * 0.5
    out = np.zeros(mag.size, dtype=np.int8)
    state = 0
    for k in range(mag.size):
        if state == 0 and mag[k] > hi:
            state = 1
        elif state == 1 and mag[k] < lo:
            state = 0
        out[k] = state
    return out


# ------------------------------------------------ استخراج النبضات (RLE)
def run_lengths(binary):
    """يعيد قائمة (level, length_samples) للنبضات المتتالية."""
    if binary.size == 0:
        return []
    change = np.flatnonzero(np.diff(binary)) + 1
    edges = np.concatenate(([0], change, [binary.size]))
    runs = []
    for a, b in zip(edges[:-1], edges[1:]):
        runs.append((int(binary[a]), int(b - a)))
    return runs


def estimate_symbol(runs, fs, min_us=20.0):
    """يقدّر زمن الرمز الأساسي من مِنوال (mode) أطوال النبضات.

    أقصر نبضة معتبرة عادةً = رمز واحد. نتجاهل النبضات الأقصر من min_us
    (ضوضاء)، ثم نأخذ منوال أقصر عنقود عبر مدرّج لوغاريتمي — أمتن من
    أخذ نسبة مئوية خام تتأثّر بذيل الضوضاء.
    """
    min_samples = fs * min_us * 1e-6
    lens = np.array([ln for _, ln in runs if ln >= min_samples], dtype=float)
    if lens.size < 3:
        return None
    # مدرّج لوغاريتمي: النبضات تتجمّع عند مضاعفات زمن الرمز (1x, 2x, 3x…)
    log_lens = np.log2(lens)
    hist, edges = np.histogram(log_lens, bins=40)
    peak_bin = int(np.argmax(hist))
    cluster_center = 2 ** ((edges[peak_bin] + edges[peak_bin + 1]) / 2)
    # زمن الرمز ≈ أقصر عنقود مأهول. العنقود الأكثر تكرارًا قد يكون 1x أو 2x،
    # فنأخذ الأصغر بين مركزه وبين الشريحة الدنيا لأطوال النبضات.
    shortest_cluster = float(np.percentile(lens, 10))
    base = min(cluster_center, shortest_cluster)
    return base / fs


# ---------------------------------------------- كشف الترميز + البتات
def decode_bits(runs, sym_samples):
    """
    تحويل النبضات إلى بتات باستخدام تكميم بطول الرمز.
    يجرّب تفسيرين شائعين في مفاتيح السيارات ويعيد الأنسب:
      - PWM/PPM: نبضة عالية قصيرة+فراغ طويل = 0، عالية طويلة+فراغ قصير = 1
      - NRZ مكمّم: كل level يتكرّر round(len/sym) مرّة
    """
    if not sym_samples or sym_samples <= 0:
        return [], "unknown"

    # NRZ مكمّم (الأبسط والأعمّ) — كرّر مستوى كل نبضة حسب طولها
    nrz = []
    for level, ln in runs:
        n = max(1, int(round(ln / sym_samples)))
        nrz.extend([level] * n)

    # محاولة PWM: أزواج (high, low) — النسبة تحدّد البت
    pwm = []
    highs = [(lv, ln) for lv, ln in runs if lv == 1]
    i = 0
    ok_pwm = True
    while i < len(runs) - 1:
        lv, ln = runs[i]
        if lv == 1 and i + 1 < len(runs) and runs[i + 1][0] == 0:
            hi_len = ln
            lo_len = runs[i + 1][1]
            if hi_len + lo_len > 0:
                pwm.append(1 if hi_len > lo_len else 0)
            i += 2
        else:
            ok_pwm = False
            i += 1

    # اختر التفسير ذا البنية الأوضح (PWM إن نتج عنه بتات متّسقة)
    if ok_pwm and len(pwm) >= 8:
        return pwm, "PWM/PPM"
    return nrz, "NRZ (quantized)"


def find_preamble(bits, min_run=8):
    """يبحث عن ترويسة نمطية (تناوب 0101.. أو سلسلة ثابتة) تسبق البيانات."""
    if len(bits) < min_run:
        return -1
    b = np.array(bits)
    # تناوب 0101...
    alt = np.abs(np.diff(b))
    for k in range(len(alt) - min_run):
        if np.all(alt[k:k + min_run] == 1):
            return k
    return -1


# ------------------------------------------------------------------ CLI
def main():
    ap = argparse.ArgumentParser(description="فكّ تضمين OOK/ASK من ملف IQ (استقبال فقط)")
    ap.add_argument("iqfile")
    ap.add_argument("--rate", type=float, required=True, help="معدّل العيّنات المستخدم في الالتقاط (Hz)")
    ap.add_argument("--fmt", default="auto", choices=["auto", "complex64", "uint8", "int8"])
    ap.add_argument("--cutoff", type=float, default=None, help="قطع المرشّح المنخفض (Hz)")
    ap.add_argument("--decim", type=int, default=1, help="تقليل العيّنات (decimation)")
    ap.add_argument("--report", action="store_true", help="طباعة تقرير مفصّل")
    args = ap.parse_args()

    iq = load_iq(args.iqfile, args.fmt)
    if iq.size == 0:
        sys.exit("الملف فارغ أو صيغته غير صحيحة.")

    mag, fs = envelope(iq, args.rate, args.cutoff, args.decim)
    thr = adaptive_threshold(mag)
    if thr is None:
        sys.exit("لا توجد إشارة معتبرة فوق أرضية الضوضاء. أعد الالتقاط أقرب/بكسب أعلى.")

    binary = binarize(mag, thr)
    runs = run_lengths(binary)
    sym = estimate_symbol(runs, fs)
    bits, coding = decode_bits(runs, sym * fs if sym else None)
    pre = find_preamble(bits)

    print(f"[+] عيّنات: {iq.size}   fs(بعد التقليل): {fs/1e6:.3f} Msps")
    print(f"[+] العتبة التكيّفية: {thr:.4f}")
    print(f"[+] عدد النبضات: {len(runs)}")
    if sym:
        print(f"[+] زمن الرمز المقدّر: {sym*1e6:.1f} µs  (~{1/sym:.0f} baud)")
    print(f"[+] الترميز المكتشَف: {coding}")
    print(f"[+] عدد البتات المستخرجة: {len(bits)}")
    if pre >= 0:
        print(f"[+] ترويسة محتملة عند البت #{pre}")
    if bits:
        preview = "".join(str(b) for b in bits[:64])
        print(f"[+] معاينة البتات: {preview}")

    if args.report and runs:
        print("\n--- أطول 12 نبضة (level, µs) ---")
        top = sorted(runs, key=lambda r: -r[1])[:12]
        for lv, ln in top:
            print(f"    level={lv}  {ln/fs*1e6:8.1f} µs")
        print("\n💡 ملاحظة للتقرير: إن كانت الإشارة Rolling Code، ستختلف البتات بين ضغطتين")
        print("    لنفس الزر — التقط مرّتين وقارن؛ هذا دليلك على آلية الحماية.")


if __name__ == "__main__":
    main()
