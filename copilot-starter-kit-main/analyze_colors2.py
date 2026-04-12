"""
Детальный анализ — проверяем outlier сэмплы и уточняем диапазоны.
Также сохраняем debug-изображения с подсветкой найденных пикселей.
"""
import cv2
import numpy as np
import os

povei_dir = os.path.join('training_data', 'povei')
debug_dir = 'debug/color_analysis'
os.makedirs(debug_dir, exist_ok=True)

# Точные диапазоны по результатам анализа
ranges = {
    '#E33789 (розовый)':    {'lo': np.array([150, 130, 150], np.uint8), 'hi': np.array([175, 255, 255], np.uint8)},
    '#430006 (тёмно-бордо)':{'lo': np.array([160, 180, 5],   np.uint8), 'hi': np.array([179, 255, 120], np.uint8)},
    '#DC0000 (ярко-красный)':{'lo': np.array([0,   180, 140], np.uint8), 'hi': np.array([6,   255, 240], np.uint8)},
}

files = sorted([f for f in os.listdir(povei_dir) if f.endswith('.png')])
print(f"Анализируем {len(files)} сэмплов\n")

# Собираем: какие сэмплы имеют комбинацию #E33789+#430006 (паттерн «повей»)
pattern_hits = []  # (fname, e33789_px, 430006_px, dc0000_px, total)

# Outlier check — сэмплы с огромным кол-вом красных пикселей
print("=== Проверка выбросов (sample_175/176/177/178) ===")
for fname in ['sample_175.png', 'sample_176.png', 'sample_177.png', 'sample_178.png']:
    fpath = os.path.join(povei_dir, fname)
    if not os.path.exists(fpath):
        continue
    img = cv2.imread(fpath)
    if img is None:
        continue
    hsv = cv2.cvtColor(img, cv2.COLOR_BGR2HSV)
    print(f"\n{fname}  size={img.shape[1]}x{img.shape[0]}")
    for rname, rng in ranges.items():
        mask = cv2.inRange(hsv, rng['lo'], rng['hi'])
        count = int(np.sum(mask > 0))
        total_px = img.shape[0] * img.shape[1]
        print(f"  {rname}: {count} px / {total_px} total = {100*count/total_px:.1f}%")
    # Save debug
    dbg = img.copy()
    for rng in ranges.values():
        mask = cv2.inRange(hsv, rng['lo'], rng['hi'])
        dbg[mask > 0] = (0, 0, 255)
    cv2.imwrite(f'{debug_dir}/{fname}', dbg)
    print(f"  -> debug saved")

print()
print("=== Сканирование всех сэмплов с новыми диапазонами ===")
for fname in files:
    fpath = os.path.join(povei_dir, fname)
    img = cv2.imread(fpath)
    if img is None:
        continue
    hsv = cv2.cvtColor(img, cv2.COLOR_BGR2HSV)

    counts = {}
    for rname, rng in ranges.items():
        mask = cv2.inRange(hsv, rng['lo'], rng['hi'])
        counts[rname] = int(np.sum(mask > 0))

    e_px = counts['#E33789 (розовый)']
    d_px = counts['#430006 (тёмно-бордо)']
    r_px = counts['#DC0000 (ярко-красный)']
    total = e_px + d_px + r_px

    pattern_hits.append((fname, e_px, d_px, r_px, total))

# Sort by total desc
pattern_hits.sort(key=lambda x: -x[4])

print(f"{'Файл':<20} {'#E33789':>8} {'#430006':>8} {'#DC0000':>8} {'Итого':>8}")
print("-" * 60)
for fname, e, d, r, tot in pattern_hits[:30]:
    marker = " <<<" if (e >= 2 and d >= 3) else ""
    print(f"{fname:<20} {e:>8} {d:>8} {r:>8} {tot:>8}{marker}")

print()
# Stats
with_pattern = [(f, e, d, r, t) for f, e, d, r, t in pattern_hits if e >= 1 and d >= 2]
print(f"Сэмплы с паттерном E33789(>=1px)+430006(>=2px): {len(with_pattern)}/{len(files)} = {100*len(with_pattern)/len(files):.1f}%")

with_any = [(f, e, d, r, t) for f, e, d, r, t in pattern_hits if t > 0]
print(f"Сэмплы хотя бы с 1 пикселем любого цвета: {len(with_any)}/{len(files)} = {100*len(with_any)/len(files):.1f}%")

# Generate combined debug for top 10 samples
print("\n=== Debug изображения для топ-10 сэмплов ===")
for fname, e, d, r, tot in pattern_hits[:10]:
    fpath = os.path.join(povei_dir, fname)
    img = cv2.imread(fpath)
    if img is None:
        continue
    hsv = cv2.cvtColor(img, cv2.COLOR_BGR2HSV)
    dbg = img.copy()
    colors_bgr = [(255, 150, 255), (0, 0, 180), (0, 0, 255)]  # pink, darkred, red
    for (rname, rng), color in zip(ranges.items(), colors_bgr):
        mask = cv2.inRange(hsv, rng['lo'], rng['hi'])
        dbg[mask > 0] = color
    cv2.imwrite(f'{debug_dir}/top_{fname}', dbg)
    print(f"  {fname}: E={e} D={d} R={r} -> {debug_dir}/top_{fname}")

print(f"\nВсе debug изображения сохранены в {debug_dir}/")

