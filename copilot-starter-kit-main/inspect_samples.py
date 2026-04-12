"""
Визуальный анализ сэмплов: делает коллаж + проверяет наличие прицела (crosshair).
Прицел — тёмный крест по центру патча.
"""
import cv2
import numpy as np
import os

def make_collage(folder, out_path, cols=16, cell=68, label_h=12):
    files = sorted([f for f in os.listdir(folder) if f.endswith('.png')])
    if not files:
        print(f"No files in {folder}")
        return
    rows = (len(files) + cols - 1) // cols
    canvas = np.ones((rows * (cell + label_h), cols * cell, 3), dtype=np.uint8) * 40

    crosshair_list = []

    for idx, fname in enumerate(files):
        img = cv2.imread(os.path.join(folder, fname))
        if img is None:
            continue
        r = idx // cols
        c = idx % cols
        img_r = cv2.resize(img, (cell, cell), interpolation=cv2.INTER_NEAREST)
        y0 = r * (cell + label_h)
        x0 = c * cell

        # Detect crosshair: dark pixels near center
        h, w = img.shape[:2]
        cx, cy = w // 2, h // 2
        gray = cv2.cvtColor(img, cv2.COLOR_BGR2GRAY)
        # Center cross region: 6x6 around center
        region = gray[max(0,cy-4):cy+4, max(0,cx-4):cx+4]
        center_dark = float(np.mean(region)) if region.size > 0 else 255
        has_crosshair = center_dark < 60  # very dark center = likely crosshair

        if has_crosshair:
            crosshair_list.append(fname)
            cv2.rectangle(img_r, (0,0), (cell-1, cell-1), (0,0,255), 2)  # red border

        canvas[y0:y0+cell, x0:x0+cell] = img_r
        # Label
        num = os.path.splitext(fname)[0].replace('sample_','')
        cv2.putText(canvas, num, (x0+1, y0+cell+label_h-2),
                    cv2.FONT_HERSHEY_SIMPLEX, 0.28, (200,200,200), 1)

    os.makedirs(os.path.dirname(out_path) if os.path.dirname(out_path) else '.', exist_ok=True)
    cv2.imwrite(out_path, canvas)
    print(f"Collage saved: {out_path}  ({len(files)} samples, {len(crosshair_list)} with crosshair)")
    if crosshair_list:
        print(f"  Crosshair detected (red border): {', '.join(crosshair_list[:20])}")
    return crosshair_list

print("=== Povei samples ===")
ch_povei = make_collage('training_data/povei', 'debug/collage_povei.png')

print("\n=== Vkusnocvet samples ===")
ch_vkusn = make_collage('training_data/vkusnocvet', 'debug/collage_vkusnocvet.png', cols=20)

# Also check center brightness distribution
print("\n=== Center brightness analysis (povei) ===")
povei_dir = 'training_data/povei'
files = sorted([f for f in os.listdir(povei_dir) if f.endswith('.png')])
bright = []
dark = []
for fname in files:
    img = cv2.imread(os.path.join(povei_dir, fname))
    if img is None:
        continue
    h, w = img.shape[:2]
    cx, cy = w//2, h//2
    gray = cv2.cvtColor(img, cv2.COLOR_BGR2GRAY)
    region = gray[max(0,cy-4):cy+5, max(0,cx-4):cx+5]
    mean_v = float(np.mean(region))
    if mean_v < 60:
        dark.append((fname, mean_v))
    else:
        bright.append((fname, mean_v))

print(f"  Dark center (<60): {len(dark)} samples  -> likely have crosshair")
print(f"  Bright center (>=60): {len(bright)} samples -> clean")
if dark:
    print(f"  Dark samples: {[f for f,v in dark[:10]]}")

