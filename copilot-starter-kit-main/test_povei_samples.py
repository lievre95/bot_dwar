"""
test_povei_samples.py — тестирует качество template matching на всех сэмплах повея.

Для каждого сэмпла: запускает find_povei_match на самом себе (self-test).
Если матч не найден или отклонён по цвету — сэмпл помечается как "слабый".

Также:
- Создаёт коллаж всех сэмплов с оценками (зелёный=pass, красный=fail)
- Выводит рекомендации по корректировке порогов
"""
import cv2
import numpy as np
import os
import sys

# ── пороги из bot.py ──────────────────────────────────────────────────────────
POVEI_MATCH_THRESHOLD = 0.55
POVEI_MATCH_SCALES    = [0.85, 0.93, 1.00, 1.08, 1.15]
POVEI_CROP_HALF       = 32

POVEI_COLOR_DARK_H_LO, POVEI_COLOR_DARK_H_HI = 160, 179
POVEI_COLOR_DARK_S_MIN                        = 180
POVEI_COLOR_DARK_V_MIN, POVEI_COLOR_DARK_V_MAX = 5, 120
POVEI_COLOR_PINK_H_LO, POVEI_COLOR_PINK_H_HI  = 150, 175
POVEI_COLOR_PINK_S_MIN                         = 130
POVEI_COLOR_PINK_V_MIN                         = 150

VERIFY_DARK_MIN = 3
VERIFY_PINK_MIN = 5


def check_colors(img):
    hsv = cv2.cvtColor(img, cv2.COLOR_BGR2HSV)
    lo_dark = np.array([POVEI_COLOR_DARK_H_LO, POVEI_COLOR_DARK_S_MIN, POVEI_COLOR_DARK_V_MIN], np.uint8)
    hi_dark = np.array([POVEI_COLOR_DARK_H_HI, 255, POVEI_COLOR_DARK_V_MAX], np.uint8)
    lo_pink = np.array([POVEI_COLOR_PINK_H_LO, POVEI_COLOR_PINK_S_MIN, POVEI_COLOR_PINK_V_MIN], np.uint8)
    hi_pink = np.array([POVEI_COLOR_PINK_H_HI, 255, 255], np.uint8)
    dark = int(np.sum(cv2.inRange(hsv, lo_dark, hi_dark) > 0))
    pink = int(np.sum(cv2.inRange(hsv, lo_pink, hi_pink) > 0))
    ok = dark >= VERIFY_DARK_MIN or pink >= VERIFY_PINK_MIN
    return ok, dark, pink


def self_match(img):
    """Template matching: img vs img (self)."""
    clahe = cv2.createCLAHE(clipLimit=2.0, tileGridSize=(4, 4))
    gray_src = clahe.apply(cv2.cvtColor(img, cv2.COLOR_BGR2GRAY))
    th, tw = img.shape[:2]
    best_val = 0.0
    for sc in POVEI_MATCH_SCALES:
        nw = max(4, int(tw * sc))
        nh = max(4, int(th * sc))
        if nw >= tw or nh >= th:
            nw, nh = max(1, tw - 2), max(1, th - 2)
        t_rs = cv2.resize(gray_src, (nw, nh), interpolation=cv2.INTER_AREA)
        try:
            res = cv2.matchTemplate(gray_src, t_rs, cv2.TM_CCOEFF_NORMED)
            _, mx, _, _ = cv2.minMaxLoc(res)
            if mx > best_val:
                best_val = mx
        except cv2.error:
            pass
    return best_val


def main():
    povei_dir = 'training_data/povei'
    os.makedirs('debug', exist_ok=True)

    files = sorted([f for f in os.listdir(povei_dir) if f.endswith('.png')],
                   key=lambda n: int(os.path.splitext(n)[0].split('_')[-1])
                                 if os.path.splitext(n)[0].split('_')[-1].isdigit() else 0)

    if not files:
        print("No samples found in training_data/povei/")
        return

    print(f"Testing {len(files)} samples...\n")

    results = []
    for fname in files:
        path = os.path.join(povei_dir, fname)
        img = cv2.imread(path)
        if img is None:
            print(f"  SKIP {fname} (unreadable)")
            continue
        h, w = img.shape[:2]
        col_ok, dark, pink = check_colors(img)
        match_conf = self_match(img)
        match_ok = match_conf >= POVEI_MATCH_THRESHOLD
        overall_ok = col_ok and match_ok
        results.append((fname, img, h, w, col_ok, dark, pink, match_conf, match_ok, overall_ok))

    passed = [r for r in results if r[9]]
    failed_color = [r for r in results if not r[4]]
    failed_match = [r for r in results if r[4] and not r[8]]

    print(f"{'='*55}")
    print(f"TOTAL: {len(results)}  PASS: {len(passed)}  FAIL_COLOR: {len(failed_color)}  FAIL_MATCH: {len(failed_match)}")
    print(f"{'='*55}")

    if failed_color:
        print(f"\nFAIL (no povei colors) — consider moving to rejected:")
        for fname, img, h, w, col_ok, dark, pink, mc, mo, ok in failed_color:
            print(f"  {fname}  dark={dark} pink={pink}  match={mc:.3f}")

    if failed_match:
        print(f"\nFAIL (match < {POVEI_MATCH_THRESHOLD}) — blurry/noisy templates:")
        for fname, img, h, w, col_ok, dark, pink, mc, mo, ok in failed_match:
            print(f"  {fname}  match={mc:.3f}  dark={dark} pink={pink}")

    # ── Коллаж всех сэмплов с оценкой ─────────────────────────────────────────
    THUMB = 72
    MARGIN = 2
    cols = 12
    rows = (len(results) + cols - 1) // cols
    canvas = np.zeros((rows * (THUMB + MARGIN + 14), cols * (THUMB + MARGIN), 3), np.uint8)

    for idx, (fname, img, h, w, col_ok, dark, pink, mc, mo, ok) in enumerate(results):
        r, c = divmod(idx, cols)
        thumb = cv2.resize(img, (THUMB, THUMB))
        y0 = r * (THUMB + MARGIN + 14)
        x0 = c * (THUMB + MARGIN)
        canvas[y0:y0+THUMB, x0:x0+THUMB] = thumb
        # Рамка: зелёная=pass, жёлтая=только матч, красная=нет цветов
        if ok:
            color = (0, 200, 0)
        elif not col_ok:
            color = (0, 0, 220)   # красная = нет цветов
        else:
            color = (0, 165, 255) # оранжевая = есть цвет, матч слабый
        cv2.rectangle(canvas, (x0, y0), (x0+THUMB-1, y0+THUMB-1), color, 2)
        # Подпись: имя файла + confidence
        label_str = f"{os.path.splitext(fname)[0].replace('sample_','')}: {mc:.2f}"
        cv2.putText(canvas, label_str, (x0+1, y0+THUMB+11),
                    cv2.FONT_HERSHEY_SIMPLEX, 0.28, color, 1)

    out = 'debug/povei_test_collage.png'
    cv2.imwrite(out, canvas)
    print(f"\nCollage saved: {out}")
    print("Green=PASS, Orange=match_fail, Red=color_fail")

    # ── Анализ распределения цветов ────────────────────────────────────────────
    dark_vals = [r[6] for r in results if r[5] > 0]  # pink vals where dark > 0
    all_dark  = [r[5] for r in results]
    all_pink  = [r[6] for r in results]
    print(f"\nColor stats:")
    print(f"  dark_px: min={min(all_dark)} max={max(all_dark)} mean={sum(all_dark)/len(all_dark):.1f}")
    print(f"  pink_px: min={min(all_pink)} max={max(all_pink)} mean={sum(all_pink)/len(all_pink):.1f}")
    print(f"  Samples with dark>0: {sum(1 for d in all_dark if d > 0)}/{len(all_dark)}")
    print(f"  Samples with pink>0: {sum(1 for p in all_pink if p > 0)}/{len(all_pink)}")

    # ── Предложения по снижению порогов ────────────────────────────────────────
    would_pass_if_lower_dark = sum(1 for r in results if not r[4] and r[5] >= 1)
    would_pass_if_lower_pink = sum(1 for r in results if not r[4] and r[5] == 0 and r[6] >= 2)
    print(f"\nIf VERIFY_DARK_MIN=1 (было {VERIFY_DARK_MIN}): дополнительно пройдут {would_pass_if_lower_dark} шт.")
    print(f"Если добавить fallback dark>=1 OR pink>=2: дополнительно {would_pass_if_lower_pink} шт.")

    # Histogram of match confidences
    match_vals = [r[7] for r in results]
    print(f"\nMatch confidence distribution (self-test):")
    bins = [(0.3, 0.45), (0.45, 0.55), (0.55, 0.65), (0.65, 0.75), (0.75, 0.85), (0.85, 1.01)]
    for lo, hi in bins:
        n = sum(1 for v in match_vals if lo <= v < hi)
        bar = '█' * n
        marker = ' ← threshold' if lo <= POVEI_MATCH_THRESHOLD < hi else ''
        print(f"  [{lo:.2f}-{hi:.2f}): {n:3d} {bar}{marker}")

    print(f"\nRecommendation:")
    if len(failed_color) > len(results) * 0.15:
        print(f"  ! {len(failed_color)} samples ({len(failed_color)*100//len(results)}%) have no povei colors — run audit_samples.py to remove them")
    if len(failed_match) > len(results) * 0.10:
        print(f"  ! {len(failed_match)} samples ({len(failed_match)*100//len(results)}%) have low match confidence — templates may be blurry/noisy")
        print(f"    Consider lowering POVEI_MATCH_THRESHOLD to {POVEI_MATCH_THRESHOLD - 0.05:.2f}")
    if len(passed) >= len(results) * 0.85:
        print(f"  OK: {len(passed)}/{len(results)} ({len(passed)*100//len(results)}%) samples pass all checks")


if __name__ == '__main__':
    main()

