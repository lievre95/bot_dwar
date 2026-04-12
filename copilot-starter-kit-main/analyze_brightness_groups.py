"""
Анализ датасетов с учётом затемнения во время добычи.

Проблема: во время добычи (dobicha) вся охота затемняется → цвета темнее.
После добычи — ярче. Это создаёт два кластера: "тёмные" и "светлые" сэмплы.

Задача: найти диапазоны HSV которые работают для ОБОИХ состояний, или
предложить adaptive-пороги с нормализацией яркости.
"""
import cv2
import numpy as np
import os
import sys

# Force UTF-8
if sys.platform.startswith('win'):
    import io
    sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8', errors='replace', line_buffering=True)

DEBUG_DIR = 'debug/brightness_analysis'
os.makedirs(DEBUG_DIR, exist_ok=True)

# ─── Конфигурация ────────────────────────────────────────────────────────────

POVEI_DIR     = os.path.join('training_data', 'povei')
VKUSNO_DIR    = os.path.join('training_data', 'vkusnocvet')

# Текущие диапазоны из bot.py (для сравнения)
CURRENT_POVEI_PINK  = {'lo': np.array([150, 130, 150], np.uint8), 'hi': np.array([175, 255, 255], np.uint8)}
CURRENT_POVEI_DARK  = {'lo': np.array([160, 180,   5], np.uint8), 'hi': np.array([179, 255, 120], np.uint8)}
CURRENT_VKUSNO      = {'lo': np.array([130,  80,  70], np.uint8), 'hi': np.array([175, 255, 230], np.uint8)}

# ─── Утилиты ─────────────────────────────────────────────────────────────────

def mean_brightness(img_bgr):
    """Средняя яркость (V канал HSV) изображения."""
    hsv = cv2.cvtColor(img_bgr, cv2.COLOR_BGR2HSV)
    return float(np.mean(hsv[:, :, 2]))

def count_mask(img_bgr, lo, hi):
    hsv = cv2.cvtColor(img_bgr, cv2.COLOR_BGR2HSV)
    mask = cv2.inRange(hsv, lo, hi)
    return int(np.sum(mask > 0)), mask

def load_samples(folder):
    files = sorted([f for f in os.listdir(folder) if f.endswith('.png')])
    samples = []
    for fname in files:
        path = os.path.join(folder, fname)
        img = cv2.imread(path)
        if img is not None:
            samples.append((fname, img))
    return samples

def split_by_brightness(samples, dark_thresh=80, bright_thresh=115):
    """
    Разделяем на 3 группы:
      dark   — V_mean < dark_thresh   (во время добычи / ночь)
      mid    — dark_thresh <= V_mean < bright_thresh
      bright — V_mean >= bright_thresh (после добычи / день)
    """
    dark, mid, bright = [], [], []
    for fname, img in samples:
        vb = mean_brightness(img)
        if vb < dark_thresh:
            dark.append((fname, img, vb))
        elif vb < bright_thresh:
            mid.append((fname, img, vb))
        else:
            bright.append((fname, img, vb))
    return dark, mid, bright

def collect_all_pixels(samples, lo, hi):
    """Собираем все HSV пиксели попавшие в диапазон."""
    pixels = []
    for fname, img in samples:
        hsv = cv2.cvtColor(img, cv2.COLOR_BGR2HSV)
        mask = cv2.inRange(hsv, lo, hi)
        ys, xs = np.where(mask > 0)
        for y, x in zip(ys, xs):
            pixels.append((int(hsv[y, x, 0]), int(hsv[y, x, 1]), int(hsv[y, x, 2])))
    return pixels

def print_group_stats(name, group):
    if not group:
        print(f"  (пусто)")
        return
    vb_vals = [vb for _, _, vb in group]
    print(f"  {name}: {len(group)} сэмплов  V_mean=[{min(vb_vals):.0f}..{max(vb_vals):.0f}]  avg={np.mean(vb_vals):.1f}")

def recommended_range(pixels, label):
    if not pixels:
        print(f"  {label}: нет пикселей")
        return None
    arr = np.array(pixels)
    h, s, v = arr[:, 0], arr[:, 1], arr[:, 2]
    # Используем percentile для устойчивости к выбросам
    h_lo, h_hi = int(np.percentile(h, 2)), int(np.percentile(h, 98))
    s_lo        = int(np.percentile(s, 5))
    v_lo, v_hi  = int(np.percentile(v, 5)), int(np.percentile(v, 95))
    print(f"  {label}: {len(pixels)} px")
    print(f"    H: {h.min()}..{h.max()}  (p2={h_lo}, p98={h_hi}, mean={h.mean():.1f}±{h.std():.1f})")
    print(f"    S: {s.min()}..{s.max()}  (p5={s_lo}, mean={s.mean():.1f}±{s.std():.1f})")
    print(f"    V: {v.min()}..{v.max()}  (p5={v_lo}, p95={v_hi}, mean={v.mean():.1f}±{v.std():.1f})")
    return {'h_lo': h_lo, 'h_hi': h_hi, 's_lo': s_lo, 'v_lo': v_lo, 'v_hi': v_hi}

def save_group_collage(group, filename, max_cols=10):
    """Сохраняем коллаж сэмплов группы с меткой яркости."""
    if not group:
        return
    imgs = []
    for fname, img, vb in group[:max_cols*4]:
        h, w = img.shape[:2]
        # Масштабируем до 64x64 если нужно
        if h != 64 or w != 64:
            img = cv2.resize(img, (64, 64))
        # Добавляем текст яркости
        dbg = img.copy()
        cv2.putText(dbg, f'{vb:.0f}', (2, 14), cv2.FONT_HERSHEY_SIMPLEX, 0.4, (0, 255, 255), 1)
        imgs.append(dbg)

    cols = min(max_cols, len(imgs))
    rows = (len(imgs) + cols - 1) // cols
    canvas = np.zeros((rows * 64 + rows * 2, cols * 64 + cols * 2, 3), dtype=np.uint8)
    for i, im in enumerate(imgs):
        r, c = divmod(i, cols)
        y0 = r * (64 + 2)
        x0 = c * (64 + 2)
        canvas[y0:y0+64, x0:x0+64] = im
    cv2.imwrite(filename, canvas)
    print(f"  Коллаж сохранён: {filename}")


# ══════════════════════════════════════════════════════════════════════════════
#  АНАЛИЗ ПОВЕЯ
# ══════════════════════════════════════════════════════════════════════════════
print("\n" + "="*70)
print("  ПОВЕЙ — анализ с учётом затемнения при добыче")
print("="*70)

povei_samples = load_samples(POVEI_DIR)
print(f"\nВсего сэмплов повея: {len(povei_samples)}")

# Показываем общее распределение яркостей
vb_all = [mean_brightness(img) for _, img in povei_samples]
vb_arr = np.array(vb_all)
print(f"\nЯркость (V_mean) по всем сэмплам повея:")
print(f"  min={vb_arr.min():.1f}  max={vb_arr.max():.1f}  mean={vb_arr.mean():.1f}  std={vb_arr.std():.1f}")
print(f"  p10={np.percentile(vb_arr,10):.1f}  p25={np.percentile(vb_arr,25):.1f}  p50={np.percentile(vb_arr,50):.1f}  p75={np.percentile(vb_arr,75):.1f}  p90={np.percentile(vb_arr,90):.1f}")

# Гистограмма яркостей
bins = [0, 30, 50, 70, 90, 110, 130, 150, 170, 200, 256]
hist, _ = np.histogram(vb_arr, bins=bins)
print(f"\n  Гистограмма яркостей:")
for i in range(len(hist)):
    bar = '█' * hist[i]
    print(f"  V=[{bins[i]:3d}..{bins[i+1]:3d}): {hist[i]:3d} сэмплов  {bar}")

# Разбиваем на группы
povei_dark, povei_mid, povei_bright = split_by_brightness(povei_samples, dark_thresh=80, bright_thresh=115)
print(f"\nРаспределение по группам (пороги: dark<80, bright>=115):")
print_group_stats("Тёмные (добыча/ночь)", povei_dark)
print_group_stats("Средние", povei_mid)
print_group_stats("Светлые (день/после добычи)", povei_bright)

# Сохраняем коллажи
save_group_collage(povei_dark,   f'{DEBUG_DIR}/povei_dark_group.png')
save_group_collage(povei_mid,    f'{DEBUG_DIR}/povei_mid_group.png')
save_group_collage(povei_bright, f'{DEBUG_DIR}/povei_bright_group.png')

# ─── ШИРОКИЕ диапазоны для широкого поиска (все пиксели в H=130..179) ───────
print("\n--- Все розово-малиновые пиксели (H=130..179, S>=50) по группам ---")
BROAD_LO = np.array([130, 50, 1], np.uint8)
BROAD_HI = np.array([179, 255, 255], np.uint8)

for gname, gsamples in [("Тёмные", [(f,i) for f,i,_ in povei_dark]),
                          ("Средние",  [(f,i) for f,i,_ in povei_mid]),
                          ("Светлые",  [(f,i) for f,i,_ in povei_bright])]:
    px = collect_all_pixels(gsamples, BROAD_LO, BROAD_HI)
    print(f"\n  Группа [{gname}] — {len(gsamples)} сэмплов:")
    recommended_range(px, "H=130..179 S>=50")

# ─── Сравниваем текущие диапазоны по группам ────────────────────────────────
print("\n\n--- Эффективность ТЕКУЩИХ диапазонов по группам ---")
print(f"\n  PINK {CURRENT_POVEI_PINK['lo']}..{CURRENT_POVEI_PINK['hi']}")
print(f"  DARK {CURRENT_POVEI_DARK['lo']}..{CURRENT_POVEI_DARK['hi']}")

for gname, gsamples in [("Тёмные",  [(f,i) for f,i,_ in povei_dark]),
                          ("Средние",  [(f,i) for f,i,_ in povei_mid]),
                          ("Светлые",  [(f,i) for f,i,_ in povei_bright])]:
    total = len(gsamples)
    if total == 0:
        continue
    pink_hits, dark_hits = 0, 0
    for fname, img in gsamples:
        p, _ = count_mask(img, CURRENT_POVEI_PINK['lo'], CURRENT_POVEI_PINK['hi'])
        d, _ = count_mask(img, CURRENT_POVEI_DARK['lo'], CURRENT_POVEI_DARK['hi'])
        if p >= 1: pink_hits += 1
        if d >= 2: dark_hits += 1
    print(f"  [{gname}] {total} сэмплов: pink≥1px={pink_hits}({100*pink_hits//total}%)  dark≥2px={dark_hits}({100*dark_hits//total}%)")

# ─── Рекомендуем расширенные диапазоны учитывающие затемнение ─────────────
print("\n\n--- Рекомендации для АДАПТИВНОГО детектора ---")

# Собираем пиксели из тёмных сэмплов с широким V-порогом
px_dark_pink = collect_all_pixels([(f,i) for f,i,_ in povei_dark],
                                   np.array([150, 80, 20], np.uint8),
                                   np.array([179, 255, 200], np.uint8))
px_bright_pink = collect_all_pixels([(f,i) for f,i,_ in povei_bright],
                                     np.array([150, 80, 20], np.uint8),
                                     np.array([179, 255, 255], np.uint8))
px_dark_dark_color = collect_all_pixels([(f,i) for f,i,_ in povei_dark],
                                         np.array([155, 100, 1], np.uint8),
                                         np.array([179, 255, 150], np.uint8))
px_bright_dark_color = collect_all_pixels([(f,i) for f,i,_ in povei_bright],
                                           np.array([155, 100, 1], np.uint8),
                                           np.array([179, 255, 200], np.uint8))

print("\n  PINK (#E33789) диапазоны по группам (H=150..179, S>=80):")
print(f"    Тёмные сэмплы  ({len(povei_dark)}):")
r_dp = recommended_range(px_dark_pink, "   розовый в тёмных")
print(f"    Светлые сэмплы ({len(povei_bright)}):")
r_bp = recommended_range(px_bright_pink, "   розовый в светлых")

print("\n  DARK (#430006) диапазоны по группам (H=155..179, S>=100):")
print(f"    Тёмные сэмплы  ({len(povei_dark)}):")
r_dd = recommended_range(px_dark_dark_color, "   тёмный в тёмных")
print(f"    Светлые сэмплы ({len(povei_bright)}):")
r_bd = recommended_range(px_bright_dark_color, "   тёмный в светлых")

# Объединённые диапазоны (union dark+bright)
all_pink = px_dark_pink + px_bright_pink
all_dark_color = px_dark_dark_color + px_bright_dark_color

if all_pink:
    arr = np.array(all_pink)
    v_all = arr[:, 2]
    s_all = arr[:, 1]
    print(f"\n  РЕКОМЕНДУЕМЫЙ диапазон PINK (объединение тёмных + светлых):")
    print(f"    H=150..175  S>={int(np.percentile(s_all,5))}  V>={int(np.percentile(v_all,5))} (p5)")
    print(f"    → Разница V: тёмные p5={int(np.percentile(np.array(px_dark_pink)[:,2] if px_dark_pink else [0], 5))}"
          f"  светлые p5={int(np.percentile(np.array(px_bright_pink)[:,2] if px_bright_pink else [255], 5))}")

if all_dark_color:
    arr = np.array(all_dark_color)
    v_all = arr[:, 2]
    s_all = arr[:, 1]
    print(f"\n  РЕКОМЕНДУЕМЫЙ диапазон DARK (объединение тёмных + светлых):")
    print(f"    H=160..179  S>={int(np.percentile(s_all,5))}  V=1..{int(np.percentile(v_all,95))} (p95)")

# ═══════════════════════════════════════════════════════════════════════════════
#  АНАЛИЗ ВКУСНОЦВЕТА
# ═══════════════════════════════════════════════════════════════════════════════
print("\n\n" + "="*70)
print("  ВКУСНОЦВЕТ — анализ с учётом затемнения при добыче")
print("="*70)

vkusno_samples = load_samples(VKUSNO_DIR)
print(f"\nВсего сэмплов вкусноцвета: {len(vkusno_samples)}")

vb_vk = np.array([mean_brightness(img) for _, img in vkusno_samples])
print(f"\nЯркость (V_mean):")
print(f"  min={vb_vk.min():.1f}  max={vb_vk.max():.1f}  mean={vb_vk.mean():.1f}  std={vb_vk.std():.1f}")
print(f"  p10={np.percentile(vb_vk,10):.1f}  p25={np.percentile(vb_vk,25):.1f}  p50={np.percentile(vb_vk,50):.1f}  p75={np.percentile(vb_vk,75):.1f}  p90={np.percentile(vb_vk,90):.1f}")

hist_vk, _ = np.histogram(vb_vk, bins=bins)
print(f"\n  Гистограмма яркостей:")
for i in range(len(hist_vk)):
    bar = '█' * hist_vk[i]
    print(f"  V=[{bins[i]:3d}..{bins[i+1]:3d}): {hist_vk[i]:3d} сэмплов  {bar}")

vk_dark, vk_mid, vk_bright = split_by_brightness(vkusno_samples, dark_thresh=80, bright_thresh=115)
print(f"\nРаспределение по группам:")
print_group_stats("Тёмные (добыча/ночь)", vk_dark)
print_group_stats("Средние", vk_mid)
print_group_stats("Светлые (день/после добычи)", vk_bright)

save_group_collage(vk_dark,   f'{DEBUG_DIR}/vkusno_dark_group.png')
save_group_collage(vk_mid,    f'{DEBUG_DIR}/vkusno_mid_group.png')
save_group_collage(vk_bright, f'{DEBUG_DIR}/vkusno_bright_group.png')

# Анализ цветовых пикселей по группам (широкий диапазон H=120..179)
VKUSNO_BROAD_LO = np.array([120, 40, 5], np.uint8)
VKUSNO_BROAD_HI = np.array([179, 255, 255], np.uint8)

print("\n--- Все пурпурно-малиновые пиксели (H=120..179, S>=40) по группам ---")
for gname, gsamples in [("Тёмные",  [(f,i) for f,i,_ in vk_dark]),
                          ("Средние",  [(f,i) for f,i,_ in vk_mid]),
                          ("Светлые",  [(f,i) for f,i,_ in vk_bright])]:
    px = collect_all_pixels(gsamples, VKUSNO_BROAD_LO, VKUSNO_BROAD_HI)
    print(f"\n  Группа [{gname}] — {len(gsamples)} сэмплов:")
    recommended_range(px, "H=120..179 S>=40")

# Текущий диапазон вкусноцвета по группам
print("\n--- Эффективность ТЕКУЩИХ диапазонов вкусноцвета по группам ---")
for gname, gsamples in [("Тёмные",  [(f,i) for f,i,_ in vk_dark]),
                          ("Средние",  [(f,i) for f,i,_ in vk_mid]),
                          ("Светлые",  [(f,i) for f,i,_ in vk_bright])]:
    total = len(gsamples)
    if total == 0:
        continue
    hits = 0
    for fname, img in gsamples:
        c, _ = count_mask(img, CURRENT_VKUSNO['lo'], CURRENT_VKUSNO['hi'])
        if c >= 15: hits += 1
    print(f"  [{gname}] {total} сэмплов: детектор (>=15px) попал={hits}({100*hits//total if total else 0}%)")

# ─── ИТОГОВЫЕ РЕКОМЕНДАЦИИ ────────────────────────────────────────────────────
print("\n\n" + "="*70)
print("  ИТОГОВЫЕ РЕКОМЕНДАЦИИ")
print("="*70)

print("""
ПРОБЛЕМА: Во время добычи всё изображение затемняется → V (яркость) падает.
Это создаёт два паттерна одного и того же цветка:
  1. ТЁМНЫЙ режим  (добыча активна / ночь): V_mean сэмпла < ~80
  2. СВЕТЛЫЙ режим (добыча завершена / день): V_mean сэмпла > ~115

РЕШЕНИЕ: Использовать нормализацию яркости фона ДО применения
цветового детектора, или расширить V-диапазоны детекторов.
""")

# Вычислим объединённые рекомендации
px_povei_all_pink = collect_all_pixels(
    povei_samples,
    np.array([148, 70, 8], np.uint8),
    np.array([179, 255, 255], np.uint8))

px_vkusno_all = collect_all_pixels(
    vkusno_samples,
    np.array([120, 40, 5], np.uint8),
    np.array([179, 255, 255], np.uint8))

if px_povei_all_pink:
    arr = np.array(px_povei_all_pink)
    h, s, v = arr[:,0], arr[:,1], arr[:,2]
    print(f"ПОВЕЙ — объединённые характеристики (H=148..179, S>=70):")
    print(f"  H: {h.min()}..{h.max()}  mean={h.mean():.1f}")
    print(f"  S: {s.min()}..{s.max()}  mean={s.mean():.1f}  p5={int(np.percentile(s,5))}")
    print(f"  V: {v.min()}..{v.max()}  mean={v.mean():.1f}  p5={int(np.percentile(v,5))}  p95={int(np.percentile(v,95))}")
    s_lo_new = max(50, int(np.percentile(s, 5)))
    v_lo_new = max(5,  int(np.percentile(v, 3)))
    print(f"\n  → Рекомендуемые константы в bot.py:")
    print(f"    POVEI_COLOR_PINK_H_LO  = {int(np.percentile(h, 2))}")
    print(f"    POVEI_COLOR_PINK_H_HI  = 179")
    print(f"    POVEI_COLOR_PINK_S_MIN = {s_lo_new}")
    print(f"    POVEI_COLOR_PINK_V_MIN = {v_lo_new}   # было 150 — теперь ловим и тёмные сэмплы")

if px_vkusno_all:
    arr = np.array(px_vkusno_all)
    h, s, v = arr[:,0], arr[:,1], arr[:,2]
    print(f"\nВКУСНОЦВЕТ — объединённые характеристики (H=120..179, S>=40):")
    print(f"  H: {h.min()}..{h.max()}  mean={h.mean():.1f}")
    print(f"  S: {s.min()}..{s.max()}  mean={s.mean():.1f}  p5={int(np.percentile(s,5))}")
    print(f"  V: {v.min()}..{v.max()}  mean={v.mean():.1f}  p5={int(np.percentile(v,5))}  p95={int(np.percentile(v,95))}")
    s_lo_new = max(40, int(np.percentile(s, 5)))
    v_lo_new = max(5,  int(np.percentile(v, 3)))
    print(f"\n  → Рекомендуемые константы в bot.py:")
    print(f"    COLOR_H_LO  = {int(np.percentile(h, 2))}")
    print(f"    COLOR_H_HI  = {int(np.percentile(h, 98))}")
    print(f"    COLOR_S_MIN = {s_lo_new}")
    print(f"    COLOR_V_MIN = {v_lo_new}   # было 70 — теперь ловим и тёмные сэмплы")

print(f"\n  Debug коллажи сохранены в: {DEBUG_DIR}/")
print("\nГотово!")

