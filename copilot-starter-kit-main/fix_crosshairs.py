"""
Очистка сэмплов от прицела (crosshair) в центре.
Прицел — тёмный крест ~5px из центра.
Заменяем его средним цветом окружающих пикселей (inpaint).
Сохраняем поверх оригиналов + делаем коллаж до/после.
"""
import cv2
import numpy as np
import os
import shutil

CROSSHAIR_DARK_THRESH = 60   # пиксели темнее этого в центральной зоне = прицел
CROSSHAIR_RADIUS      = 7    # радиус зоны вокруг центра для поиска прицела
INPAINT_RADIUS        = 4    # радиус inpaint заливки

def remove_crosshair(img):
    """Убирает прицел из центра патча методом inpaint."""
    h, w = img.shape[:2]
    cx, cy = w // 2, h // 2
    gray = cv2.cvtColor(img, cv2.COLOR_BGR2GRAY)

    # Маска прицела: тёмные пиксели в центральной зоне
    mask = np.zeros((h, w), dtype=np.uint8)
    region_y1 = max(0, cy - CROSSHAIR_RADIUS)
    region_y2 = min(h, cy + CROSSHAIR_RADIUS + 1)
    region_x1 = max(0, cx - CROSSHAIR_RADIUS)
    region_x2 = min(w, cx + CROSSHAIR_RADIUS + 1)

    for y in range(region_y1, region_y2):
        for x in range(region_x1, region_x2):
            if gray[y, x] < CROSSHAIR_DARK_THRESH:
                mask[y, x] = 255

    if np.sum(mask) == 0:
        return img, False  # нет прицела

    # Inpaint — заполняем тёмные пиксели цветами соседей
    result = cv2.inpaint(img, mask, INPAINT_RADIUS, cv2.INPAINT_TELEA)
    return result, True


def process_folder(folder, backup_suffix='_with_crosshair'):
    files = sorted([f for f in os.listdir(folder) if f.endswith('.png')])
    fixed = 0
    skipped = 0

    before_imgs = []
    after_imgs  = []

    for fname in files:
        path = os.path.join(folder, fname)
        img = cv2.imread(path)
        if img is None:
            continue

        result, had_crosshair = remove_crosshair(img)

        if had_crosshair:
            # Бэкап оригинала
            backup_dir = folder + backup_suffix
            os.makedirs(backup_dir, exist_ok=True)
            shutil.copy2(path, os.path.join(backup_dir, fname))
            # Сохраняем чистый
            cv2.imwrite(path, result)
            fixed += 1
            before_imgs.append((fname, img))
            after_imgs.append((fname, result))
        else:
            skipped += 1

    print(f"  {folder}: fixed={fixed}, clean={skipped}, total={fixed+skipped}")
    print(f"  Backups saved to: {folder}{backup_suffix}/")

    # Коллаж до/после для первых 20 исправленных
    if before_imgs:
        cell = 68
        n = min(20, len(before_imgs))
        canvas = np.ones((cell * 2 + 20, n * cell, 3), dtype=np.uint8) * 30
        for i, ((fname, b), (_, a)) in enumerate(zip(before_imgs[:n], after_imgs[:n])):
            bx = i * cell
            canvas[0:cell, bx:bx+cell] = cv2.resize(b, (cell, cell))
            canvas[cell+20:cell*2+20, bx:bx+cell] = cv2.resize(a, (cell, cell))
            num = os.path.splitext(fname)[0].replace('sample_','')
            cv2.putText(canvas, num, (bx+2, cell-2), cv2.FONT_HERSHEY_SIMPLEX, 0.28, (200,200,50), 1)
        # Separating line
        canvas[cell:cell+20, :] = 20
        cv2.putText(canvas, 'BEFORE', (2, 12), cv2.FONT_HERSHEY_SIMPLEX, 0.4, (100,255,100), 1)
        cv2.putText(canvas, 'AFTER',  (2, cell+32), cv2.FONT_HERSHEY_SIMPLEX, 0.4, (100,255,100), 1)
        out = f"debug/crosshair_fix_{os.path.basename(folder)}.png"
        os.makedirs('debug', exist_ok=True)
        cv2.imwrite(out, canvas)
        print(f"  Before/after preview: {out}")

    return fixed


print("=== Removing crosshairs from training samples ===\n")
total = 0
total += process_folder('training_data/povei')
print()
total += process_folder('training_data/vkusnocvet')
print(f"\nTotal fixed: {total} samples")
print("Done. Bot will use clean templates on next run.")

