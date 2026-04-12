"""
Диагностика — смотрим реальные значения пикселей в пропущенных сэмплах.
Ищем почему паттерн не срабатывает.
"""
import cv2
import numpy as np
import os

povei_dir = os.path.join('training_data', 'povei')

# Проверяем несколько "хороших" сэмплов которые должны быть повеем
check_files = [
    'sample_0.png', 'sample_2.png', 'sample_9.png', 'sample_11.png',
    'sample_35.png', 'sample_38.png', 'sample_49.png', 'sample_53.png',
    'sample_100.png', 'sample_101.png', 'sample_162.png'
]

# Широкие диапазоны для розово-малинового (#E33789 -> HSV H=166, S=193, V=227)
# Тёмно-бордового (#430006 -> HSV H=177, S=255, V=67)
# Розово-красного диапазона: H=140..179 (охватывает и E33789 и 430006)

print("=== Детальный анализ пикселей в диапазоне H=140..179 ===\n")

for fname in check_files:
    fpath = os.path.join(povei_dir, fname)
    img = cv2.imread(fpath)
    if img is None:
        print(f"{fname}: не найден")
        continue
    hsv = cv2.cvtColor(img, cv2.COLOR_BGR2HSV)
    h_ch = hsv[:,:,0]
    s_ch = hsv[:,:,1]
    v_ch = hsv[:,:,2]

    # Все пиксели в диапазоне H=140..179
    mask_hue = (h_ch >= 140) & (h_ch <= 179)
    ys, xs = np.where(mask_hue)

    if len(ys) == 0:
        print(f"{fname}: нет пикселей H=140..179")
        continue

    hvals = h_ch[ys, xs]
    svals = s_ch[ys, xs]
    vvals = v_ch[ys, xs]

    print(f"{fname}: {len(ys)} px в H=140..179")
    print(f"  H: {hvals.min()}..{hvals.max()}  S: {svals.min()}..{svals.max()}  V: {vvals.min()}..{vvals.max()}")

    # Группируем по зонам
    # Зона "розовый" H=150..175, S>100, V>120
    pink_mask = (h_ch >= 150) & (h_ch <= 175) & (s_ch > 100) & (v_ch > 120)
    # Зона "тёмно-бордо" H=160..179, S>150, V<130
    dark_mask = (h_ch >= 160) & (h_ch <= 179) & (s_ch > 150) & (v_ch < 130)

    pink_px = int(np.sum(pink_mask))
    dark_px = int(np.sum(dark_mask))
    print(f"  Розовый (H=150..175, S>100, V>120): {pink_px} px")
    print(f"  Тёмно-бордо (H=160..179, S>150, V<130): {dark_px} px")

    # Показываем топ-10 пикселей по H
    sorted_idx = np.argsort(hvals)[-10:]
    print(f"  Топ по H: ", end="")
    for i in sorted_idx:
        print(f"H={hvals[i]} S={svals[i]} V={vvals[i]}", end="  ")
    print()
    print()

print("\n=== Что ищут константы из bot.py ===")
print("PINK: H=150..175, S>=130, V>=150")
print("DARK: H=160..179, S>=180, V=5..120")
print()

# Проверяем с текущими порогами но без требования паттерна
POVEI_COLOR_PINK_H_LO  = 150
POVEI_COLOR_PINK_H_HI  = 175
POVEI_COLOR_PINK_S_MIN = 130
POVEI_COLOR_PINK_V_MIN = 150
POVEI_COLOR_DARK_H_LO  = 160
POVEI_COLOR_DARK_H_HI  = 179
POVEI_COLOR_DARK_S_MIN = 180
POVEI_COLOR_DARK_V_MIN = 5
POVEI_COLOR_DARK_V_MAX = 120

files = sorted([f for f in os.listdir(povei_dir) if f.endswith('.png')])
print(f"Статистика по всем {len(files)} сэмплам:")
pink_counts = []
dark_counts = []
for fname in files:
    fpath = os.path.join(povei_dir, fname)
    img = cv2.imread(fpath)
    if img is None:
        continue
    hsv = cv2.cvtColor(img, cv2.COLOR_BGR2HSV)
    lo_pink = np.array([POVEI_COLOR_PINK_H_LO, POVEI_COLOR_PINK_S_MIN, POVEI_COLOR_PINK_V_MIN], np.uint8)
    hi_pink = np.array([POVEI_COLOR_PINK_H_HI, 255, 255], np.uint8)
    lo_dark = np.array([POVEI_COLOR_DARK_H_LO, POVEI_COLOR_DARK_S_MIN, POVEI_COLOR_DARK_V_MIN], np.uint8)
    hi_dark = np.array([POVEI_COLOR_DARK_H_HI, 255, POVEI_COLOR_DARK_V_MAX], np.uint8)
    p = int(np.sum(cv2.inRange(hsv, lo_pink, hi_pink) > 0))
    d = int(np.sum(cv2.inRange(hsv, lo_dark, hi_dark) > 0))
    pink_counts.append(p)
    dark_counts.append(d)

pa = np.array(pink_counts)
da = np.array(dark_counts)
print(f"  Розовый (PINK): >0 px в {np.sum(pa>0)}/{len(files)} сэмплах, медиана={np.median(pa):.0f}, макс={pa.max()}")
print(f"  Тёмно-бордо (DARK): >0 px в {np.sum(da>0)}/{len(files)} сэмплах, медиана={np.median(da):.0f}, макс={da.max()}")
print(f"  Оба >0: {np.sum((pa>0)&(da>0))}/{len(files)} сэмплов")
print(f"  PINK>=1 AND DARK>=1: {np.sum((pa>=1)&(da>=1))}/{len(files)}")
print(f"  PINK>=1 AND DARK>=2: {np.sum((pa>=1)&(da>=2))}/{len(files)}")
print(f"  PINK>=2 AND DARK>=2: {np.sum((pa>=2)&(da>=2))}/{len(files)}")

