import cv2, numpy as np, glob, os

all_patches = glob.glob('debug/povei_REJECTED_*.png')
all_patches.sort(key=lambda x: -int(x.split('_')[-1].split('.')[0]))
print(f'Found {len(all_patches)} patches, analyzing latest 5:')

for p in all_patches[:5]:
    img = cv2.imread(p)
    if img is None:
        print(f'{p}: not found'); continue
    hsv = cv2.cvtColor(img, cv2.COLOR_BGR2HSV)
    h, s, v = hsv[:,:,0], hsv[:,:,1], hsv[:,:,2]
    mask = v > 20
    if mask.sum() == 0:
        print(f'{os.path.basename(p)}: all black'); continue

    # Ищем пиксели с S>=80 (насыщенные) — именно такие у повея
    sat_mask = (s >= 80) & mask
    print(f'\n{os.path.basename(p)}: {img.shape[1]}x{img.shape[0]}')
    print(f'  All px H: {h[mask].min()}-{h[mask].max()} mean={h[mask].mean():.0f}')
    print(f'  Sat px (S>=80): {sat_mask.sum()}')
    if sat_mask.sum() > 0:
        print(f'    H: {h[sat_mask].min()}-{h[sat_mask].max()} mean={h[sat_mask].mean():.0f}')
        print(f'    S: {s[sat_mask].min()}-{s[sat_mask].max()} mean={s[sat_mask].mean():.0f}')
        print(f'    V: {v[sat_mask].min()}-{v[sat_mask].max()} mean={v[sat_mask].mean():.0f}')

    # Проверяем текущие диапазоны
    dark_mask = (h >= 160) & (h <= 179) & (s >= 130) & (v >= 5) & (v <= 135)
    pink_mask = (h >= 150) & (h <= 179) & (s >= 130) & (v >= 20)
    print(f'  Current dark (H160-179,S>=130,V5-135): {dark_mask.sum()}px')
    print(f'  Current pink (H150-179,S>=130,V>=20):  {pink_mask.sum()}px')

    # Широкий поиск: любые пиксели с красным/малиновым оттенком
    wide_red = ((h <= 10) | (h >= 150)) & (s >= 60) & (v >= 10)
    print(f'  Wide red/pink (H<=10 or H>=150, S>=60, V>=10): {wide_red.sum()}px')
    if wide_red.sum() > 0:
        wh = h[wide_red]
        print(f'    H values sample: {sorted(set(wh.tolist()))[:20]}')

    b, g, r = img[:,:,0], img[:,:,1], img[:,:,2]
    print(f'  BGR mean (all): B={b[mask].mean():.0f} G={g[mask].mean():.0f} R={r[mask].mean():.0f}')

