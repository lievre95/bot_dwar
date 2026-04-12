"""
Создание шаблонов для бота.
Открывает скриншоты игры — кликай ЛКМ на вкусноцвет/повей-траву.
R — следующий скриншот, Z — отменить, Q — сохранить и выйти.
"""
import cv2, numpy as np, os, json, glob

PATCH_SIZE = 80
HALF = PATCH_SIZE // 2
OUT_DIR = "templates"
os.makedirs(OUT_DIR, exist_ok=True)

screenshots = sorted(glob.glob("training-data/runtime/*.png"))
if not screenshots:
    print("Нет скриншотов в training-data/runtime/"); exit(1)

print(f"Найдено {len(screenshots)} скриншотов")
print("ЛКМ — отметить ресурс  |  R — следующий  |  Z — отменить  |  Q — выйти+сохранить")

templates = []
saved_count = 0
shot_idx = 0

def mouse_cb(event, x, y, flags, param):
    global saved_count
    if event != cv2.EVENT_LBUTTONDOWN:
        return
    scale = param['scale']
    orig  = param['orig']
    disp  = param['disp']
    ox = int(x / scale);  oy = int(y / scale)
    h, w = orig.shape[:2]
    x1 = max(0, ox-HALF);  y1 = max(0, oy-HALF)
    x2 = min(w, ox+HALF);  y2 = min(h, oy+HALF)
    patch = orig[y1:y2, x1:x2].copy()
    fname = f"{OUT_DIR}/template_{saved_count}.png"
    cv2.imwrite(fname, patch)
    templates.append({"x": ox, "y": oy, "image": fname,
                       "width": x2-x1, "height": y2-y1})
    saved_count += 1
    print(f"  [+] {fname}  orig=({ox},{oy})")
    cv2.rectangle(disp, (x-HALF, y-HALF), (x+HALF, y+HALF), (0,255,0), 2)
    cv2.putText(disp, f"#{saved_count}", (x-HALF, y-HALF-4),
                cv2.FONT_HERSHEY_SIMPLEX, 0.5, (0,255,0), 1)
    cv2.imshow(WIN, disp)

WIN = "Отметь ресурсы: ЛКМ=сохранить  R=след  Z=отмена  Q=выход"

while shot_idx < len(screenshots):
    path = screenshots[shot_idx]
    print(f"\n[{shot_idx+1}/{len(screenshots)}] {os.path.basename(path)}")
    img = cv2.imread(path)
    if img is None:
        shot_idx += 1; continue
    h, w = img.shape[:2]
    scale = min(1.0, 1400/w, 850/h)
    dw, dh = int(w*scale), int(h*scale)
    disp = cv2.resize(img, (dw, dh), interpolation=cv2.INTER_AREA)
    param = {'orig': img.copy(), 'disp': disp, 'scale': scale}
    cv2.namedWindow(WIN, cv2.WINDOW_NORMAL)
    cv2.resizeWindow(WIN, dw, dh)
    cv2.setMouseCallback(WIN, mouse_cb, param)
    cv2.imshow(WIN, disp)
    print(f"  {w}x{h} -> показывается {dw}x{dh} (scale={scale:.2f})")

    while True:
        k = cv2.waitKey(30) & 0xFF
        if k in (ord('q'), 27):
            shot_idx = len(screenshots); break
        elif k in (ord('r'), ord('n'), ord(' ')):
            shot_idx += 1; break
        elif k == ord('z') and templates:
            t = templates.pop(); saved_count -= 1
            try: os.remove(t['image'])
            except: pass
            print(f"  [-] Отменён {t['image']}")
            fresh = cv2.resize(img, (dw, dh), interpolation=cv2.INTER_AREA)
            for tt in templates:
                tx=int(tt['x']*scale); ty=int(tt['y']*scale)
                cv2.rectangle(fresh,(tx-HALF,ty-HALF),(tx+HALF,ty+HALF),(0,255,0),2)
            param['disp'][:] = fresh
            cv2.imshow(WIN, fresh)

cv2.destroyAllWindows()

if templates:
    json.dump(templates, open("recorded_samples.json","w",encoding="utf-8"),
              indent=2, ensure_ascii=False)
    print(f"\n=== Сохранено {len(templates)} шаблонов -> recorded_samples.json ===")
    print("Запусти: npm run bot -> Запустить")
else:
    print("\nНичего не сохранено.")
