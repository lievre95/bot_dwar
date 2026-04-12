"""
normalize_samples.py — нормализация и объединение сэмплов.

Что делает:
  1. Все сэмплы vkusnocvet (из training_data/vkusnocvet/ и templates/) → 64×64
  2. Все сэмплы povei (из training_data/povei/) → 64×64
  3. Перемещает templates/ → training_data/vkusnocvet/ (единое место)
  4. Удаляет дубликаты по хэшу изображения
  5. Пересохраняет с последовательными именами sample_0.png, sample_1.png, ...
  6. Создаёт резервную копию в backup_samples/

Запуск: python normalize_samples.py
"""

import cv2
import os
import shutil
import hashlib
import numpy as np

TARGET_SIZE_VKUSN = 64   # целевой размер для вкусноцвета
TARGET_SIZE_POVEI = 64   # целевой размер для повея

BACKUP_DIR = 'backup_samples'


def img_hash(img):
    return hashlib.md5(img.tobytes()).hexdigest()


def center_crop_resize(img, target):
    """Обрезает по центру до квадрата, затем ресайзит до target×target."""
    h, w = img.shape[:2]
    # Обрезаем по меньшей стороне (квадрат по центру)
    side = min(h, w)
    y0 = (h - side) // 2
    x0 = (w - side) // 2
    cropped = img[y0:y0+side, x0:x0+side]
    return cv2.resize(cropped, (target, target), interpolation=cv2.INTER_AREA)


def process_dir(src_dir, target_size, label, extra_dirs=None):
    """
    Собирает все PNG из src_dir и extra_dirs,
    нормализует до target_size×target_size,
    дедуплицирует, пересохраняет.
    Возвращает количество сохранённых файлов.
    """
    if not os.path.isdir(src_dir):
        print(f"  [skip] {src_dir} not found")
        return 0

    # Резервная копия
    backup = os.path.join(BACKUP_DIR, label)
    if os.path.isdir(src_dir):
        print(f"  Backing up {src_dir} → {backup}")
        if os.path.exists(backup):
            shutil.rmtree(backup)
        shutil.copytree(src_dir, backup)

    # Собираем все исходные файлы
    all_dirs = [src_dir] + (extra_dirs or [])
    all_files = []
    for d in all_dirs:
        if os.path.isdir(d):
            for f in sorted(os.listdir(d)):
                if f.endswith('.png'):
                    all_files.append(os.path.join(d, f))

    print(f"  Collecting {len(all_files)} files from {all_dirs}")

    # Загружаем, нормализуем, дедупликация
    seen_hashes = set()
    normalized = []
    for path in all_files:
        img = cv2.imread(path)
        if img is None:
            print(f"    [skip] can't read {path}")
            continue
        h, w = img.shape[:2]
        if h == target_size and w == target_size:
            normed = img.copy()
        else:
            normed = center_crop_resize(img, target_size)
        hsh = img_hash(normed)
        if hsh in seen_hashes:
            print(f"    [dup] {os.path.basename(path)} ({w}x{h}) — skipped")
            continue
        seen_hashes.add(hsh)
        normalized.append((normed, os.path.basename(path), w, h))

    print(f"  After dedup: {len(normalized)} unique samples")

    # Очищаем src_dir и пересохраняем
    for f in os.listdir(src_dir):
        if f.endswith('.png'):
            os.remove(os.path.join(src_dir, f))

    saved = 0
    for i, (img, orig_name, ow, oh) in enumerate(normalized):
        out_path = os.path.join(src_dir, f"sample_{i}.png")
        cv2.imwrite(out_path, img)
        print(f"    {orig_name} ({ow}x{oh}) → sample_{i}.png ({target_size}x{target_size})")
        saved += 1

    return saved


def main():
    os.makedirs(BACKUP_DIR, exist_ok=True)
    print("=" * 60)
    print("NORMALIZE SAMPLES")
    print("=" * 60)

    # ── vkusnocvet: объединяем training_data/vkusnocvet/ + templates/ ──
    print("\n[vkusnocvet]")
    vkusn_dir = os.path.join('training_data', 'vkusnocvet')
    os.makedirs(vkusn_dir, exist_ok=True)

    # Резервная копия templates/
    if os.path.isdir('templates'):
        tpl_backup = os.path.join(BACKUP_DIR, 'templates')
        print(f"  Backing up templates/ → {tpl_backup}")
        if os.path.exists(tpl_backup):
            shutil.rmtree(tpl_backup)
        shutil.copytree('templates', tpl_backup)

    n = process_dir(vkusn_dir, TARGET_SIZE_VKUSN, 'vkusnocvet',
                    extra_dirs=['templates'])
    print(f"  → {n} vkusnocvet samples saved to {vkusn_dir}/")

    # Очищаем templates/ (файлы теперь в training_data/vkusnocvet/)
    if os.path.isdir('templates'):
        tpl_files = [f for f in os.listdir('templates') if f.endswith('.png')]
        for f in tpl_files:
            os.remove(os.path.join('templates', f))
        print(f"  Cleared {len(tpl_files)} files from templates/ (merged into vkusnocvet/)")

    # ── povei ──────────────────────────────────────────────────────────
    print("\n[povei]")
    povei_dir = os.path.join('training_data', 'povei')
    os.makedirs(povei_dir, exist_ok=True)
    n = process_dir(povei_dir, TARGET_SIZE_POVEI, 'povei')
    print(f"  → {n} povei samples saved to {povei_dir}/")

    print("\n" + "=" * 60)
    print("DONE. Резервная копия в backup_samples/")
    print(f"Запусти бота — он подгрузит нормализованные шаблоны 64x64.")
    print("=" * 60)


if __name__ == '__main__':
    main()

