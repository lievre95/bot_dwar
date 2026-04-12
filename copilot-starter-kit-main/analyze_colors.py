"""
Анализ сэмплов повея — поиск цветов #E33789, #430006, #DC0000
и вычисление точных HSV диапазонов для детектора.
"""
import cv2
import numpy as np
import os

# Target colors in HEX -> BGR (OpenCV)
# #E33789 -> R=227, G=55,  B=137  -> BGR=(137, 55, 227)
# #430006 -> R=67,  G=0,   B=6    -> BGR=(6,   0,  67)
# #DC0000 -> R=220, G=0,   B=0    -> BGR=(0,   0,  220)

target_bgr = [
    (137, 55,  227),  # #E33789 pink/magenta
    (6,   0,   67),   # #430006 dark red
    (0,   0,   220),  # #DC0000 red
]
target_names = ['#E33789', '#430006', '#DC0000']

# Convert to HSV
print("=== Target colors HSV ===")
target_hsv_vals = []
for name, bgr in zip(target_names, target_bgr):
    pixel = np.array([[list(bgr)]], dtype=np.uint8)
    hsv = cv2.cvtColor(pixel, cv2.COLOR_BGR2HSV)[0][0]
    target_hsv_vals.append(hsv)
    print(f"  {name}  BGR={bgr}  ->  HSV H={hsv[0]} S={hsv[1]} V={hsv[2]}")

print()

# Scan all povei samples — collect all matching pixels
povei_dir = os.path.join('training_data', 'povei')
files = sorted([f for f in os.listdir(povei_dir) if f.endswith('.png')])

tolerance_h = 12   # hue tolerance
tolerance_s = 60   # saturation tolerance
tolerance_v = 60   # value tolerance

all_hits = {name: [] for name in target_names}
sample_scores = []

# Collect all HSV pixel values from ALL samples that match ANY target color
all_matching_pixels = []  # (H, S, V) tuples

print(f"=== Scanning {len(files)} samples ===")
for fname in files:
    path = os.path.join(povei_dir, fname)
    img = cv2.imread(path)
    if img is None:
        continue
    hsv = cv2.cvtColor(img, cv2.COLOR_BGR2HSV)
    h_ch = hsv[:, :, 0]
    s_ch = hsv[:, :, 1]
    v_ch = hsv[:, :, 2]

    scores = {}
    combined_mask = np.zeros(h_ch.shape, dtype=np.uint8)

    for name, bgr, tgt in zip(target_names, target_bgr, target_hsv_vals):
        th, ts, tv = int(tgt[0]), int(tgt[1]), int(tgt[2])
        lo = np.array([max(0, th - tolerance_h),
                       max(0, ts - tolerance_s),
                       max(0, tv - tolerance_v)], np.uint8)
        hi = np.array([min(179, th + tolerance_h),
                       min(255, ts + tolerance_s),
                       min(255, tv + tolerance_v)], np.uint8)
        mask = cv2.inRange(hsv, lo, hi)
        count = int(np.sum(mask > 0))
        scores[name] = count
        if count > 0:
            all_hits[name].append(fname)
            combined_mask = cv2.bitwise_or(combined_mask, mask)

    # Collect actual pixel values for matched pixels
    ys, xs = np.where(combined_mask > 0)
    for y, x in zip(ys, xs):
        all_matching_pixels.append((int(h_ch[y, x]), int(s_ch[y, x]), int(v_ch[y, x])))

    total = sum(scores.values())
    if total > 0:
        sample_scores.append((fname, scores, total))

print(f"Samples with color hits (top 20 by count):")
for fname, scores, total in sorted(sample_scores, key=lambda x: -x[2])[:20]:
    s = '  |  '.join(f"{n}={c}" for n, c in scores.items() if c > 0)
    print(f"  {fname}: {s}  (total={total})")

print()
print("=== Coverage ===")
for name in target_names:
    pct = 100.0 * len(all_hits[name]) / len(files)
    print(f"  {name}: found in {len(all_hits[name])}/{len(files)} samples ({pct:.1f}%)")

print()
print("=== Combined HSV range of ALL matching pixels ===")
if all_matching_pixels:
    arr = np.array(all_matching_pixels)
    h_vals = arr[:, 0]
    s_vals = arr[:, 1]
    v_vals = arr[:, 2]
    print(f"  H: min={h_vals.min()}  max={h_vals.max()}  mean={h_vals.mean():.1f}  std={h_vals.std():.1f}")
    print(f"  S: min={s_vals.min()}  max={s_vals.max()}  mean={s_vals.mean():.1f}  std={s_vals.std():.1f}")
    print(f"  V: min={v_vals.min()}  max={v_vals.max()}  mean={v_vals.mean():.1f}  std={v_vals.std():.1f}")
    print()
    # Recommended ranges (mean ± 2std, clamped)
    h_lo = max(0,   int(h_vals.mean() - 2*h_vals.std()))
    h_hi = min(179, int(h_vals.mean() + 2*h_vals.std()))
    s_lo = max(0,   int(s_vals.mean() - 2*s_vals.std()))
    v_lo = max(0,   int(v_vals.mean() - 2*v_vals.std()))
    print(f"  Recommended HSV range: H={h_lo}..{h_hi}  S>={s_lo}  V>={v_lo}")
else:
    print("  No matching pixels found!")

print()
print("=== Per-color HSV pixel stats ===")
for name, bgr, tgt in zip(target_names, target_bgr, target_hsv_vals):
    th, ts, tv = int(tgt[0]), int(tgt[1]), int(tgt[2])
    lo = np.array([max(0, th - tolerance_h), max(0, ts - tolerance_s), max(0, tv - tolerance_v)], np.uint8)
    hi = np.array([min(179, th + tolerance_h), min(255, ts + tolerance_s), min(255, tv + tolerance_v)], np.uint8)
    pixels = []
    for fname in files:
        path = os.path.join(povei_dir, fname)
        img = cv2.imread(path)
        if img is None:
            continue
        hsv = cv2.cvtColor(img, cv2.COLOR_BGR2HSV)
        mask = cv2.inRange(hsv, lo, hi)
        ys2, xs2 = np.where(mask > 0)
        for y2, x2 in zip(ys2, xs2):
            pixels.append((int(hsv[y2, x2, 0]), int(hsv[y2, x2, 1]), int(hsv[y2, x2, 2])))
    if pixels:
        pa = np.array(pixels)
        print(f"  {name}: {len(pixels)} px — H={pa[:,0].min()}..{pa[:,0].max()} S={pa[:,1].min()}..{pa[:,1].max()} V={pa[:,2].min()}..{pa[:,2].max()}")
    else:
        print(f"  {name}: 0 pixels found")

