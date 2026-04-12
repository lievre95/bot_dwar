"""
Финальная проверка нового детектора повея (тёмно-бордо #430006 как главный маркер).
"""
import cv2
import numpy as np
import os

POVEI_COLOR_PINK_H_LO  = 150
POVEI_COLOR_PINK_H_HI  = 175
POVEI_COLOR_PINK_S_MIN = 130
POVEI_COLOR_PINK_V_MIN = 150
POVEI_COLOR_DARK_H_LO  = 160
POVEI_COLOR_DARK_H_HI  = 179
POVEI_COLOR_DARK_S_MIN = 180
POVEI_COLOR_DARK_V_MIN = 5
POVEI_COLOR_DARK_V_MAX = 120
POVEI_COLOR_MIN_AREA   = 2
POVEI_COLOR_MAX_AREA   = 5000
POVEI_COLOR_MORPH_K    = 5
POVEI_COLOR_DARK_MIN_PX = 2

povei_dir = os.path.join('training_data', 'povei')
files = sorted([f for f in os.listdir(povei_dir) if f.endswith('.png')])

detected = 0
not_detected = []

for fname in files:
    fpath = os.path.join(povei_dir, fname)
    img = cv2.imread(fpath)
    if img is None:
        continue
    hsv = cv2.cvtColor(img, cv2.COLOR_BGR2HSV)

    lo_dark = np.array([POVEI_COLOR_DARK_H_LO, POVEI_COLOR_DARK_S_MIN, POVEI_COLOR_DARK_V_MIN], np.uint8)
    hi_dark = np.array([POVEI_COLOR_DARK_H_HI, 255, POVEI_COLOR_DARK_V_MAX], np.uint8)
    mask_dark = cv2.inRange(hsv, lo_dark, hi_dark)

    lo_pink = np.array([POVEI_COLOR_PINK_H_LO, POVEI_COLOR_PINK_S_MIN, POVEI_COLOR_PINK_V_MIN], np.uint8)
    hi_pink = np.array([POVEI_COLOR_PINK_H_HI, 255, 255], np.uint8)
    mask_pink = cv2.inRange(hsv, lo_pink, hi_pink)

    k = cv2.getStructuringElement(cv2.MORPH_ELLIPSE, (POVEI_COLOR_MORPH_K, POVEI_COLOR_MORPH_K))
    mask_dark_closed = cv2.morphologyEx(mask_dark, cv2.MORPH_CLOSE, k)
    mask_pink_closed = cv2.morphologyEx(mask_pink, cv2.MORPH_CLOSE, k)
    mask_all = cv2.bitwise_or(mask_dark_closed, mask_pink_closed)

    num_labels, labels_map, stats, centroids = cv2.connectedComponentsWithStats(mask_all, connectivity=8)

    found = False
    best_score = 0
    for lbl in range(1, num_labels):
        area = int(stats[lbl, cv2.CC_STAT_AREA])
        if area < POVEI_COLOR_MIN_AREA or area > POVEI_COLOR_MAX_AREA:
            continue
        cx_roi = int(centroids[lbl][0])
        cy_roi = int(centroids[lbl][1])
        comp_mask = (labels_map == lbl).astype(np.uint8)
        dark_px = int(np.sum(cv2.bitwise_and(mask_dark, comp_mask) > 0))
        pink_px = int(np.sum(cv2.bitwise_and(mask_pink, comp_mask) > 0))
        pad = 28
        h_r, w_r = mask_dark.shape[:2]
        rx1 = max(0, cx_roi - pad); ry1 = max(0, cy_roi - pad)
        rx2 = min(w_r, cx_roi + pad); ry2 = min(h_r, cy_roi + pad)
        dark_px = max(dark_px, int(np.sum(mask_dark[ry1:ry2, rx1:rx2] > 0)))
        pink_px = max(pink_px, int(np.sum(mask_pink[ry1:ry2, rx1:rx2] > 0)))
        if dark_px >= POVEI_COLOR_DARK_MIN_PX:
            found = True
            best_score = max(best_score, dark_px * 2 + pink_px)

    if found:
        detected += 1
        print(f"  OK: {fname}  dark={int(np.sum(mask_dark>0))}  pink={int(np.sum(mask_pink>0))}  score={best_score}")
    else:
        not_detected.append(fname)
        d = int(np.sum(mask_dark > 0)); p = int(np.sum(mask_pink > 0))
        if d > 0 or p > 0:
            print(f"  MISS: {fname}  dark={d}  pink={p}  (labels={num_labels-1})")

print()
print(f"=== ИТОГ ===")
print(f"Детектировано:    {detected}/{len(files)} = {100*detected/len(files):.1f}%")
print(f"Не детектировано: {len(not_detected)}/{len(files)}")
if not_detected:
    print(f"Пропущенные ({len(not_detected)}): {', '.join(not_detected[:15])}{'...' if len(not_detected) > 15 else ''}")
