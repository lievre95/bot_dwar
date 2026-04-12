"""
Верификация новых порогов: сравнение OLD vs NEW по группам яркости.
"""
import cv2
import numpy as np
import os
import sys

if sys.platform.startswith('win'):
    import io
    sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8', errors='replace', line_buffering=True)

POVEI_DIR  = os.path.join('training_data', 'povei')
VKUSNO_DIR = os.path.join('training_data', 'vkusnocvet')

# ── ПОВЕЙ: старые пороги ──────────────────────────────────────────────────────
OLD_PINK = {'lo': np.array([150, 130, 150], np.uint8), 'hi': np.array([175, 255, 255], np.uint8)}
OLD_DARK = {'lo': np.array([160, 180,   5], np.uint8), 'hi': np.array([179, 255, 120], np.uint8)}

# ── ПОВЕЙ: новые пороги (из анализа датасета) ─────────────────────────────────
NEW_PINK = {'lo': np.array([150, 130,  20], np.uint8), 'hi': np.array([179, 255, 255], np.uint8)}
NEW_DARK = {'lo': np.array([160, 130,   5], np.uint8), 'hi': np.array([179, 255, 135], np.uint8)}

# ── ВКУСНОЦВЕТ: старые пороги ─────────────────────────────────────────────────
OLD_VK = {'lo': np.array([130,  80,  70], np.uint8), 'hi': np.array([175, 255, 230], np.uint8)}

# ── ВКУСНОЦВЕТ: новые пороги ──────────────────────────────────────────────────
NEW_VK = {'lo': np.array([124,  50,  34], np.uint8), 'hi': np.array([175, 255, 230], np.uint8)}


def load_and_group(folder):
    files = sorted([f for f in os.listdir(folder) if f.endswith('.png')])
    groups = {'dark (V<80)': [], 'mid (80-115)': [], 'bright (V>115)': []}
    for fname in files:
        img = cv2.imread(os.path.join(folder, fname))
        if img is None:
            continue
        vb = float(np.mean(cv2.cvtColor(img, cv2.COLOR_BGR2HSV)[:, :, 2]))
        if vb < 80:
            groups['dark (V<80)'].append((fname, img, vb))
        elif vb >= 115:
            groups['bright (V>115)'].append((fname, img, vb))
        else:
            groups['mid (80-115)'].append((fname, img, vb))
    return groups


def count_hits(img, lo, hi, min_px=1):
    hsv = cv2.cvtColor(img, cv2.COLOR_BGR2HSV)
    return int(np.sum(cv2.inRange(hsv, lo, hi) > 0)) >= min_px


# ══════════════════════════════════════════════════════════════════════════════
#  ПОВЕЙ
# ══════════════════════════════════════════════════════════════════════════════
print("=" * 75)
print("  ПОВЕЙ — OLD vs NEW пороги по группам яркости")
print("=" * 75)
print(f"{'Группа':<16} {'N':<5} | {'OLD pink>=1':<12} {'OLD dark>=2':<12} {'OLD any':<10} | {'NEW pink>=1':<12} {'NEW dark>=2':<12} {'NEW any':<10}")
print("-" * 95)

povei_groups = load_and_group(POVEI_DIR)
for gname, glist in povei_groups.items():
    n = len(glist)
    if n == 0:
        print(f"  {gname:<14} {n:<5} | — (нет сэмплов)")
        continue
    op = od = oa = np_ = nd = na = 0
    for _, img, _ in glist:
        old_p = count_hits(img, OLD_PINK['lo'], OLD_PINK['hi'], 1)
        old_d = count_hits(img, OLD_DARK['lo'], OLD_DARK['hi'], 2)
        new_p = count_hits(img, NEW_PINK['lo'], NEW_PINK['hi'], 1)
        new_d = count_hits(img, NEW_DARK['lo'], NEW_DARK['hi'], 2)
        if old_p: op += 1
        if old_d: od += 1
        if old_p or old_d: oa += 1
        if new_p: np_ += 1
        if new_d: nd += 1
        if new_p or new_d: na += 1
    print(f"  {gname:<14} {n:<5} | {op:>5}({100*op//n:>3}%)   {od:>5}({100*od//n:>3}%)   {oa:>4}({100*oa//n:>3}%) | "
          f"{np_:>5}({100*np_//n:>3}%)   {nd:>5}({100*nd//n:>3}%)   {na:>4}({100*na//n:>3}%)")

# Итог по всем
all_povei = [(f, i, v) for g in povei_groups.values() for f, i, v in g]
n = len(all_povei)
op = od = oa = np_ = nd = na = 0
for _, img, _ in all_povei:
    old_p = count_hits(img, OLD_PINK['lo'], OLD_PINK['hi'], 1)
    old_d = count_hits(img, OLD_DARK['lo'], OLD_DARK['hi'], 2)
    new_p = count_hits(img, NEW_PINK['lo'], NEW_PINK['hi'], 1)
    new_d = count_hits(img, NEW_DARK['lo'], NEW_DARK['hi'], 2)
    if old_p: op += 1
    if old_d: od += 1
    if old_p or old_d: oa += 1
    if new_p: np_ += 1
    if new_d: nd += 1
    if new_p or new_d: na += 1
print("-" * 95)
print(f"  {'ИТОГО':<14} {n:<5} | {op:>5}({100*op//n:>3}%)   {od:>5}({100*od//n:>3}%)   {oa:>4}({100*oa//n:>3}%) | "
      f"{np_:>5}({100*np_//n:>3}%)   {nd:>5}({100*nd//n:>3}%)   {na:>4}({100*na//n:>3}%)")

# ══════════════════════════════════════════════════════════════════════════════
#  ВКУСНОЦВЕТ
# ══════════════════════════════════════════════════════════════════════════════
print()
print("=" * 75)
print("  ВКУСНОЦВЕТ — OLD vs NEW пороги по группам яркости")
print("=" * 75)
print(f"{'Группа':<16} {'N':<5} | {'OLD >=15px':<12} | {'NEW >=15px':<12}")
print("-" * 55)

vkusno_groups = load_and_group(VKUSNO_DIR)
for gname, glist in vkusno_groups.items():
    n = len(glist)
    if n == 0:
        print(f"  {gname:<14} {n:<5} | — (нет сэмплов)")
        continue
    oh = nh = 0
    for _, img, _ in glist:
        hsv = cv2.cvtColor(img, cv2.COLOR_BGR2HSV)
        oc = int(np.sum(cv2.inRange(hsv, OLD_VK['lo'], OLD_VK['hi']) > 0))
        nc = int(np.sum(cv2.inRange(hsv, NEW_VK['lo'], NEW_VK['hi']) > 0))
        if oc >= 15: oh += 1
        if nc >= 15: nh += 1
    print(f"  {gname:<14} {n:<5} | {oh:>5}({100*oh//n:>3}%)   | {nh:>5}({100*nh//n:>3}%)")

all_vk = [(f, i, v) for g in vkusno_groups.values() for f, i, v in g]
n = len(all_vk)
oh = nh = 0
for _, img, _ in all_vk:
    hsv = cv2.cvtColor(img, cv2.COLOR_BGR2HSV)
    oc = int(np.sum(cv2.inRange(hsv, OLD_VK['lo'], OLD_VK['hi']) > 0))
    nc = int(np.sum(cv2.inRange(hsv, NEW_VK['lo'], NEW_VK['hi']) > 0))
    if oc >= 15: oh += 1
    if nc >= 15: nh += 1
print("-" * 55)
print(f"  {'ИТОГО':<14} {n:<5} | {oh:>5}({100*oh//n:>3}%)   | {nh:>5}({100*nh//n:>3}%)")

print()
print("Итог:")
print("  ПОВЕЙ PINK: V_MIN снижен 150→20 — тёмный режим теперь детектируется")
print("  ПОВЕЙ DARK: S_MIN снижен 180→130 — больше пикселей в обоих режимах")
print("  ВКУСНОЦВЕТ: S_MIN 80→50, V_MIN 70→34 — тёмные сэмплы тоже детектируются")

