"""
audit_samples.py — анализирует все сэмплы training_data/povei/
и выявляет "плохие" (не содержат характерных цветов повея).
Плохие сэмплы перемещаются в training_data/povei_rejected/.
Создаёт collage с пометками good/bad для визуального контроля.
"""
import cv2, numpy as np, os, shutil

POVEI_DIR   = 'training_data/povei'
REJECT_DIR  = 'training_data/povei_rejected'
DEBUG_DIR   = 'debug'

# HSV пороги повея (из bot.py)
DARK_H_LO, DARK_H_HI = 160, 179
DARK_S_MIN            = 180
DARK_V_MIN, DARK_V_MAX = 5, 120

PINK_H_LO, PINK_H_HI = 150, 175
PINK_S_MIN            = 130
PINK_V_MIN            = 150

# Минимум пикселей для признания сэмпла "хорошим"
VERIFY_DARK_MIN = 3
VERIFY_PINK_MIN = 5


def check_sample(img):
    hsv = cv2.cvtColor(img, cv2.COLOR_BGR2HSV)
    lo_dark = np.array([DARK_H_LO, DARK_S_MIN, DARK_V_MIN], np.uint8)
    hi_dark = np.array([DARK_H_HI, 255,        DARK_V_MAX], np.uint8)
    lo_pink = np.array([PINK_H_LO, PINK_S_MIN, PINK_V_MIN], np.uint8)
    hi_pink = np.array([PINK_H_HI, 255,        255       ], np.uint8)
    dark_px = int(np.sum(cv2.inRange(hsv, lo_dark, hi_dark) > 0))
    pink_px = int(np.sum(cv2.inRange(hsv, lo_pink, hi_pink) > 0))
    is_good = dark_px >= VERIFY_DARK_MIN or pink_px >= VERIFY_PINK_MIN
    return is_good, dark_px, pink_px


def main():
    os.makedirs(REJECT_DIR, exist_ok=True)
    os.makedirs(DEBUG_DIR, exist_ok=True)

    files = sorted([f for f in os.listdir(POVEI_DIR) if f.endswith('.png')],
                   key=lambda n: int(os.path.splitext(n)[0].split('_')[-1])
                                 if os.path.splitext(n)[0].split('_')[-1].isdigit() else 0)

    good_list = []
    bad_list  = []

    for fname in files:
        path = os.path.join(POVEI_DIR, fname)
        img  = cv2.imread(path)
        if img is None:
            print(f"  UNREADABLE: {fname}")
            bad_list.append((fname, 0, 0))
            continue
        is_good, dark, pink = check_sample(img)
        if is_good:
            good_list.append((fname, dark, pink, img))
        else:
            bad_list.append((fname, dark, pink))
            print(f"  BAD: {fname}  dark={dark} pink={pink}  size={img.shape[1]}x{img.shape[0]}")

    print(f"\nRESULT: {len(good_list)} good, {len(bad_list)} bad out of {len(files)} total")

    # Перемещаем плохие сэмплы в rejected
    moved = 0
    for fname, dark, pink, *_ in [(n,d,p) for n,d,p in bad_list]:
        src = os.path.join(POVEI_DIR, fname)
        dst = os.path.join(REJECT_DIR, fname)
        if os.path.exists(src):
            shutil.move(src, dst)
            moved += 1
    print(f"Moved {moved} bad samples to {REJECT_DIR}/")

    # Сохраняем collage из хороших сэмплов
    if good_list:
        THUMB = 64
        cols = 16
        rows = (len(good_list) + cols - 1) // cols
        canvas = np.zeros((rows * (THUMB + 2), cols * (THUMB + 2), 3), np.uint8)
        for idx, (fname, dark, pink, img) in enumerate(good_list):
            r, c = divmod(idx, cols)
            thumb = cv2.resize(img, (THUMB, THUMB))
            y1, x1 = r * (THUMB + 2), c * (THUMB + 2)
            canvas[y1:y1+THUMB, x1:x1+THUMB] = thumb
            # Зелёная рамка
            cv2.rectangle(canvas, (x1, y1), (x1+THUMB-1, y1+THUMB-1), (0, 200, 0), 1)
        out = os.path.join(DEBUG_DIR, 'povei_good_collage.png')
        cv2.imwrite(out, canvas)
        print(f"Good collage saved: {out}")

    # Сохраняем collage из плохих (из папки rejected)
    bad_imgs = []
    for fname, dark, pink in bad_list:
        path = os.path.join(REJECT_DIR, fname)
        img  = cv2.imread(path)
        if img is not None:
            bad_imgs.append((fname, dark, pink, img))
    if bad_imgs:
        THUMB = 64
        cols = 8
        rows = (len(bad_imgs) + cols - 1) // cols
        canvas = np.zeros((rows * (THUMB + 2), cols * (THUMB + 2), 3), np.uint8)
        for idx, (fname, dark, pink, img) in enumerate(bad_imgs):
            r, c = divmod(idx, cols)
            thumb = cv2.resize(img, (THUMB, THUMB))
            y1, x1 = r * (THUMB + 2), c * (THUMB + 2)
            canvas[y1:y1+THUMB, x1:x1+THUMB] = thumb
            # Красная рамка
            cv2.rectangle(canvas, (x1, y1), (x1+THUMB-1, y1+THUMB-1), (0, 0, 220), 1)
        out = os.path.join(DEBUG_DIR, 'povei_bad_collage.png')
        cv2.imwrite(out, canvas)
        print(f"Bad collage saved: {out}")

    print("\nDone. Review debug/povei_good_collage.png and debug/povei_bad_collage.png")
    print(f"If bad_collage contains real povei — move files back from {REJECT_DIR}/ to {POVEI_DIR}/")


if __name__ == '__main__':
    main()

