"""
DwarBot — Electron/Python CV bot for dwar.ru hunt farming.
Launch via electron-main.js (npm run bot).

Record mode (--record): watches mouse, LMB saves 96x96 patch.
Auto mode: finds saved patches on screenshot, clicks.
"""

import cv2
import numpy as np
import pyautogui
import time
import sys
import argparse
import json
import os
import glob
import threading
import ctypes
import winsound
import logging
from mss import mss
from pynput import mouse

# Force UTF-8 on Windows to avoid encoding crashes
if sys.platform.startswith('win'):
    import io
    sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8', errors='replace', line_buffering=True)
    sys.stderr = io.TextIOWrapper(sys.stderr.buffer, encoding='utf-8', errors='replace', line_buffering=True)

pyautogui.FAILSAFE = False

# ─── file logger ────────────────────────────────────────────────────────────────
os.makedirs('logs', exist_ok=True)
_file_logger = logging.getLogger('dwarbot')
_file_logger.setLevel(logging.DEBUG)
_fh = logging.FileHandler('logs/bot_session.log', encoding='utf-8', mode='a')
_fh.setFormatter(logging.Formatter('%(asctime)s %(message)s', datefmt='%H:%M:%S'))
_file_logger.addHandler(_fh)
# ────────────────────────────────────────────────────────────────────────────────

# ─── constants ──────────────────────────────────────────────────────────────────
MATCH_THRESHOLD   = 0.45   # any match above this goes to circle check
WEAK_THRESHOLD    = 0.45   # same — single entry threshold
GATHER_WAIT            = 41.0   # seconds to wait for resource gather (vkusnocvet cooldown)
GATHER_WAIT_POVEI      = 50.0   # повей — то же время, dobicha gone завершит раньше если добыча кончилась
GATHER_CHECK_INTERVAL  = 0.2   # sec between dobicha.png polls (снижено для быстрой реакции на исчезновение)
GATHER_CONFIRM_HITS    = 2     # consecutive hits needed to confirm gathering started
GATHER_EARLY_MISS_SECS = 2.0   # if dobicha not seen within this many seconds → abort, find next
GATHER_RESOURCE_GONE_CONSEC = 99999  # ОТКЛЮЧЕНО — ранняя отмена по dobicha miss заблокирована
COLOR_GONE_CONSEC_REQUIRED  = 99999  # ОТКЛЮЧЕНО — ранняя отмена по цвету заблокирована
GATHER_REF_DELAY_SECS       = 1.0  # задержка перед снятием эталона цвета — ждём пока анимация затухнет
GATHER_SCAN_INTERVAL   = 1.0   # sec between background arrow-key scrolls WHILE gathering
GATHER_SCAN_SCROLL     = 14    # scroll notches during background scan
CYCLE_SLEEP       = 1.5    # pause between search cycles
SCALES            = [0.85, 1.00, 1.15]  # scales for matching
CROP_HALF         = 32     # половина патча = 64×64 px — единый стандарт для всех сэмплов

SCROLL_EVERY        = 1      # scroll every N empty cycles (1 = every cycle)
SCROLL_AMOUNT       = 5       # нажатий стрелки за один вызов скролла
SCROLL_REPEATS      = 1       # вызовов скролла за раз
SCROLL_PAUSE        = 0.05   # пауза между нажатиями стрелки (сек)
SCROLL_CYCLE_STEPS  = 5      # 5 шагов вниз + 5 шагов вверх = один полный цикл
CLICK_COOLDOWN    = 42.5   # seconds to ignore already-clicked position
CLICK_RADIUS      = 55     # pixels — zone around clicked point
DEAD_COOLDOWN     = 120.0  # seconds to ignore dead zone (no gather)
COLOR_REJECT_COOLDOWN = 30.0  # seconds to suppress positions rejected by color verify (false-positive cooldown)
COLOR_REJECT_RADIUS   = 30    # px radius for color-reject suppression (smaller than CLICK_RADIUS)
GATHER_MOVE_WAIT  = 0.8    # pause after click before check (sec)
CLICK_AWAY_COOLDOWN = 30.0 # минимальный интервал между click_away (сек) — не мешать игре чаще нужного
GATHER_UI_TPL     = 'dobicha.png'   # gather window template
GATHER_BANNER_TPL = 'banner.png'    # gather banner — второй индикатор добычи
GATHER_UI_THRESH  = 0.38   # gather window detection threshold (снижен: реальный матч ~0.418)
GATHER_BANNER_THRESH = 0.50  # banner detection threshold (понижен: реальный score ~0.53)
GATHER_BANNER_CHECK_INTERVAL = 5.0  # каждые N сек проверяем баннер — если нет, прыжок на новый ресурс
GATHER_UI_ZONE    = 0.35   # search only in center fraction of screen (0.35 = middle 35% each side)
PROVERKA_TPL      = 'proverka.png'  # inspection window template — BEEP on detection
PROVERKA_THRESH   = 0.70   # detection threshold
PROVERKA_CHECK_INTERVAL = 1.5  # sec between inspection checks
PROVERKA_BEEP_HZ  = 1100   # beep frequency (Hz)
PROVERKA_BEEP_MS  = 800    # beep duration (ms)
NEUDACHA_TPL      = 'neudacha.png'  # окно неудачи — нужно закрыть и продолжить
NEUDACHA_THRESH   = 0.70            # порог обнаружения
NEUDACHA_CHECK_INTERVAL = 1.5       # интервал проверки (сек)
# Смещение кнопки «Закрыть» (крестик) от левого верхнего угла найденного шаблона (px capture).
# neudacha.png = 385x96px. Крестик закрытия обычно в правом верхнем углу окна.
# Если не попадает точно — поправь NEUDACHA_CLOSE_OFFSET_X/Y в config/dwar-selectors.json
NEUDACHA_CLOSE_OFFSET_X = 370   # правый край шаблона + чуть правее (крестик)
NEUDACHA_CLOSE_OFFSET_Y = 8     # верхний край шаблона + немного вниз
BOI_TPL               = 'boi.png'   # окно "бои" — останавливает скролл и поиск
BOI_THRESH            = 0.70        # порог обнаружения
BOI_CHECK_INTERVAL    = 2.0         # интервал проверки (сек)
BLOCK_TPL             = 'block.png' # окно блока/нападения — тоже останавливает поиск
BLOCK_THRESH          = 0.55        # порог (большой шаблон — порог выше)
# Selection circle detector (single click -> check)
CIRCLE_CHECK_WAIT = 0.8    # sec to wait after single click
CIRCLE_RADIUS_MIN = 20     # min selection circle radius (px)
CIRCLE_RADIUS_MAX = 44     # max selection circle radius (px) — less than bot square (~54)
CIRCLE_SEARCH_R   = 80     # search radius around click point (px)
CIRCLE_MIN_BRIGHT = 80     # min ring brightness (0-255)
CIRCLE_MIN_CONTRAST = 20.0 # min ring-vs-inner contrast to confirm circle
CIRCLE_SAVE_DEBUG = True   # save ROI image when circle confirmed (debug)
# ── Bright-blob detector (resource glow detection) ──────────────────────────────
# Resources in dwar.ru glow white/bright ON green grass.
# Calibrated against Location_1.png (resources) vs Location_2.png (empty):
#   Grass filter + bright glow → 57 blobs in L1, 1 blob in L2
# REDUCED thresholds to catch more resources, then filter by shape+occupation
BLOB_V_THRESH     = 180    # HSV Value threshold — pixels brighter than this (was 210, too strict)
BLOB_S_THRESH     = 80     # HSV Saturation max — near-white glow (was 70)
BLOB_MIN_AREA     = 50     # min blob area in pixels (was 60, slightly relaxed)
BLOB_MAX_AREA     = 3000   # max blob area (was 8000, stricter to avoid UI + large noise)
BLOB_MORPH_K      = 9      # morphology close kernel to merge nearby bright pixels
# Green grass mask parameters (flowers grow ONLY on green ground)
BLOB_GRASS_H_LO   = 25     # HSV Hue min for green grass (yellow-green)
BLOB_GRASS_H_HI   = 88     # HSV Hue max for green grass
BLOB_GRASS_S_MIN  = 35     # min saturation (not grey/white)
BLOB_GRASS_V_MIN  = 35     # min brightness (not too dark)
BLOB_GRASS_V_MAX  = 210    # max brightness (not glowing itself)
BLOB_GRASS_DILATE = 40     # dilate grass mask by this many px to include flowers above
# UI strip margins to ignore (in pixels from each edge of capture area)
BLOB_IGNORE_BOTTOM_PX = 220  # bottom inventory/hotbar (includes bottom-right UI panel)
BLOB_IGNORE_TOP_PX    = 135  # top minimap/title bar (~130px on 1343h screen)
BLOB_IGNORE_LEFT_PX   = 80   # left edge — left UI buttons panel
BLOB_IGNORE_RIGHT_PX  = 500  # right edge — right UI panel (inventory, chat, ~500px wide)
# ── Hunt window ROI — exact pixel margins given by user ───────────────────────
# Margins from capture area edges (px, absolute — NOT fractions):
#   Top:    200px from top
#   Left:   80px from left   (narrow left UI bar)
#   Bottom: 180px from bottom
#   Right:  580px from right  (scrollbar list + right UI panel)
# NOTE: these are defaults; overridden by --hunt-* CLI args or CMD_SET_HUNT_ROI stdin command.
HUNT_TOP_PX    = 200   # px from top of capture
HUNT_LEFT_PX   = 80    # px from left of capture
HUNT_BOTTOM_PX = 180   # px from bottom of capture
HUNT_RIGHT_PX  = 580   # px from right of capture (scroll-tab list is on the RIGHT side)
# ── Color-blob detector: vkusnocvet flower colors ─────────────────────────────
# #A551BC (purple)       → HSV H=144 S=145 V=188  → range H=130..155
# #830E43 (dark crimson) → HSV H=166 S=228 V=131  → range H=155..175
# Анализ 35 сэмплов (тёмные/добыча + светлые/день):
#   Тёмные (добыча активна, V_mean<80): H=124..158, S>=51, V=34..131
#   Светлые (после добычи, V_mean>115): H=125..163, S>=48, V=78..248
#   → Объединённый диапазон H=124..159, S>=50, V>=34
COLOR_H_LO   = 120   # HSV Hue min (OpenCV 0-179) — расширен для охвата пурпурных оттенков
COLOR_H_HI   = 175   # HSV Hue max — оставлен широким для охвата тёмно-бордового хвоста
COLOR_S_MIN  = 45    # min saturation — снижено чуть больше для добычи в тени
COLOR_V_MIN  = 30    # min brightness — снижено для затемнённых сэмплов (добыча)
COLOR_V_MAX  = 235   # max brightness (exclude overexposed UI)
COLOR_MIN_AREA  = 25    # min blob area px — снижено для надёжного обнаружения
COLOR_MAX_AREA  = 6000  # max blob area (UI elements)
COLOR_MORPH_K   = 5     # morphology close kernel
# Vkusnocvet must have at least this many matching color pixels to be confirmed
# (analysis: vkusnocvet mean=141px, min=71px — threshold 20px даёт уверенный запас)
COLOR_MIN_PIXELS = 20   # min color pixels required in a blob to count as vkusnocvet
# ── Povei template matching ────────────────────────────────────────────────────
POVEI_MATCH_THRESHOLD = 0.70  # raise threshold — many templates cause false grass matches at 0.55-0.69
POVEI_MATCH_SCALES    = [0.85, 0.93, 1.00, 1.08, 1.15]  # масштабы для вариативности
POVEI_CROP_HALF       = 32    # половина размера патча для повея (иконка ~32-40px)
POVEI_SEARCH_IN_HUNT_ONLY = True
# ── Цветовой детектор повея по паттерну E33789 + 430006 ───────────────────────
# Анализ 92 сэмплов training_data/povei/ с учётом затемнения при добыче:
#
#   ТЁМНЫЕ сэмплы (V_mean<80, 39шт — добыча активна / ночь):
#     PINK: pink≥1px = 1/39 (2%) ← текущий V_MIN=150 отрезает тёмные!
#     DARK: dark≥2px = 39/39 (100%) ← работает отлично
#     Розовые пиксели: H=150..179, S>=132, V=25..131  (среднее V=75)
#     Тёмные пиксели:  H=160..179, S>=132, V=8..131   (среднее V=59)
#
#   СВЕТЛЫЕ сэмплы (V_mean>=115, 21шт — после добычи / день):
#     PINK: pink≥1px = 21/21 (100%)
#     DARK: dark≥2px = 21/21 (100%)
#     Розовые пиксели: H=150..179, S>=130, V=29..255  (среднее V=138)
#     Тёмные пиксели:  H=159..179, S>=130, V=15..112  (среднее V=66)
#
#   ВЫВОД: PINK V_MIN=150 полностью пропускает тёмный режим → снизить до 20.
#          DARK работает в обоих режимах (V уже начинается с 5).
# Стратегия: ищем блобы по тёмно-бордовому (#430006) — он есть везде.
# Дополнительно проверяем розовый (#E33789) рядом.
# Fallback: если dark=0 но pink >= POVEI_COLOR_PINK_ONLY_MIN — тоже считаем.
# #DC0000 отключён — даёт ложные срабатывания на других объектах.
POVEI_COLOR_PINK_H_LO    = 150   # #E33789 розовый — H min
POVEI_COLOR_PINK_H_HI    = 179   # #E33789 розовый — H max (расширен до 179)
POVEI_COLOR_PINK_S_MIN   = 130   # мин. насыщенность
POVEI_COLOR_PINK_V_MIN   = 20    # мин. яркость — было 150, снижено для тёмного режима (добыча)
POVEI_COLOR_DARK_H_LO    = 160   # #430006 тёмно-бордово — H min
POVEI_COLOR_DARK_H_HI    = 179   # #430006 тёмно-бордово — H max
POVEI_COLOR_DARK_S_MIN   = 130   # мин. насыщенность — было 180, снижено (p5 из анализа)
POVEI_COLOR_DARK_V_MIN   = 5     # мин. яркость (очень тёмный)
POVEI_COLOR_DARK_V_MAX   = 135   # макс. яркость — было 120, расширено (p95=131 + запас)
POVEI_COLOR_MIN_AREA     = 1     # мин. площадь компонента (px²) — пиксели очень редкие
POVEI_COLOR_MAX_AREA     = 5000  # макс. площадь (крупнее = не повей)
POVEI_COLOR_MORPH_K      = 5     # морфология для объединения соседних пикселей
POVEI_COLOR_DARK_MIN_PX  = 2    # мин. тёмно-бордовых пикселей (основной маркер)
POVEI_COLOR_PINK_ONLY_MIN = 2   # мин. розовых пикселей если dark=0 (fallback)
# ──────────────────────────────────────────────────────────────────────────────


class DwarBot:
    def __init__(self, record_mode=False, capture_bounds=None,
                 cursor_bounds=None, scale=1.0, stop_token='',
                 max_cycles=0, dry_run=False, record_label='recorded',
                 hunt_left=None, hunt_top=None, hunt_right=None, hunt_bottom=None):

        self.running         = False
        self.record_mode     = record_mode
        self.scale           = scale
        self.stop_token      = stop_token
        self.max_cycles      = int(max_cycles or 0)
        self.dry_run         = bool(dry_run)
        self.record_label    = record_label or 'recorded'
        self._is_windows     = sys.platform.startswith('win')

        # Hunt ROI margins (physical px from capture edges) — overridable per instance
        self.hunt_left   = int(hunt_left)   if hunt_left   is not None else HUNT_LEFT_PX
        self.hunt_top    = int(hunt_top)    if hunt_top    is not None else HUNT_TOP_PX
        self.hunt_right  = int(hunt_right)  if hunt_right  is not None else HUNT_RIGHT_PX
        self.hunt_bottom = int(hunt_bottom) if hunt_bottom is not None else HUNT_BOTTOM_PX

        self.capture_bounds  = capture_bounds or {'x': 0, 'y': 0, 'width': 1920, 'height': 1080}
        self.cursor_bounds   = cursor_bounds  or {'x': 0, 'y': 0, 'width': 1920, 'height': 1080}


        self.recorded_samples   = []
        self.sample_templates   = []
        self._tpl_cache         = []  # preprocessed templates for enhanced matching
        self._saved_on_exit     = False
        self._last_emit_ts      = 0.0
        self._last_emit_pos     = (-9999, -9999)
        self._cycle_index       = 0
        self._no_match_streak   = 0
        self._scroll_steps_down = 0   # счётчик для совместимости (BG scroll лог)
        self._scroll_steps_up   = 0
        self._scroll_going_up   = False
        self._scroll_pos        = 0   # позиция в цикле 0..9 (0-4=вниз, 5-9=вверх)
        self._last_click_gx     = None   # экранная X последнего клика (для скролла стрелками)
        self._last_click_gy     = None   # экранная Y последнего клика
        self._sweep_points      = []
        self._sweep_idx         = 0
        self.resources_gathered = 0
        # (lx, ly, ts) — recently clicked points (cooldown)
        self._clicked_recently  = []
        # (lx, ly, ts) — dead zones: clicked but no gather
        self._dead_zones        = []
        # (lx, ly, ts) — positions rejected by povei color verify (avoid re-matching)
        self._color_reject_zones = []
        # {(cx,cy): count} — сколько раз позиция была отклонена по цвету (перманентный бан после 4 отклонений)
        self._color_reject_counts = {}
        # (cx, cy) — перманентно забаненные ложные матчи (UI-элементы похожие на повей)
        self._perm_reject_pos  = set()
        # Gather window template (dobicha.png)
        self._gather_ui_tpl     = None
        self._load_gather_ui_tpl()
        # Gather banner template (banner.png) — второй индикатор добычи
        self._gather_banner_tpl = None
        self._load_gather_banner_tpl()
        # Inspection template (proverka.png) — background monitor with beep
        self._proverka_tpl      = None
        self._proverka_alerted  = False   # prevent beeping every frame
        self._load_proverka_tpl()
        # Neudacha template (neudacha.png) — background monitor, auto-close
        self._neudacha_tpl      = None
        self._neudacha_closing  = False   # prevent double-click
        self._load_neudacha_tpl()
        # Boi template (boi.png) — паузирует весь поиск пока окно боя видно
        self._boi_tpl           = None
        self._boi_active        = False   # True = окно боя видно, поиск приостановлен
        self._load_boi_tpl()
        # Block template (block.png) — окно нападения, тоже паузирует поиск
        self._block_tpl         = None
        self._load_block_tpl()
        # Кандидаты найденные во время фоновых сканов во время добычи
        # [(cx, cy, label, score), ...] — используются в _search_and_gather_next как приоритет
        self._bg_candidates     = []
        # ── Chat ROI monitor ────────────────────────────────────────────────

        self._log(f"capture={self.capture_bounds}  scale={self.scale}")
        self._log(f"cursor={self.cursor_bounds}")
        self._log(f"max_cycles={self.max_cycles}  dry_run={self.dry_run}")
        if self.record_mode:
            self._log(f"record_label={self.record_label}")
        if self.stop_token:
            self._log(f"stop_token={self.stop_token[:6]}...")


        self.load_samples()

    # ── utilities ───────────────────────────────────────────────────────────────

    def _log(self, msg):
        print(msg, flush=True)
        try:
            _file_logger.info(msg)
        except Exception:
            pass

    def _emit(self, msg):
        print(msg, flush=True)

    def _load_povei_thresholds(self):
        pass  # HSV-пороги для повея больше не используются — только template matching

    def _emit_candidates(self, screenshot, exclude_pos=None):
        """
        Fast scan for next targets — color blobs only (no template matching).
        Includes both vkusnocvet (magenta) and povei (green) candidates with confidence.
        Format: SHOW_CANDIDATES:x1,y1,label1,conf1|x2,y2,label2,conf2|...
        """
        if screenshot is None:
            return
        exclude = exclude_pos or []
        candidates = []

        # Vkusnocvet — color blobs (only those with enough pixels to be real vkusnocvet)
        for cx, cy, area in self.find_color_blobs(screenshot, exclude):
            conf = min(0.99, area / 400.0)
            candidates.append((cx, cy, 'vkusn', round(conf, 2)))

        # Povei — color blobs (dark-bordeaux + pink markers)
        # Skip positions already claimed by vkusnocvet
        vkusn_positions = [(cx, cy) for cx, cy, lbl, _ in candidates if lbl == 'vkusn']
        for cx, cy, score in self.find_povei_color_blobs(screenshot, exclude):
            # Don't show povei label if the same spot is already detected as vkusnocvet
            if any(abs(cx - vx) < 55 and abs(cy - vy) < 55 for vx, vy in vkusn_positions):
                continue
            conf = min(0.99, score / 20.0)
            candidates.append((cx, cy, 'povei', round(conf, 2)))

        if not candidates:
            self._log("Candidates: 0 found (color blobs only)")
            return

        # Deduplicate by proximity (55px), povei preferred over vkusn when overlapping
        deduped = []
        for cx, cy, lbl, cf in sorted(candidates, key=lambda x: (-({'povei':1}.get(x[2],0)), -x[3])):
            if any(abs(cx - dx) < 55 and abs(cy - dy) < 55 for dx, dy, *_ in deduped):
                continue
            deduped.append((cx, cy, lbl, cf))

        parts = '|'.join(f"{cx},{cy},{lbl},{cf}" for cx, cy, lbl, cf in deduped[:8])
        self._emit(f"SHOW_CANDIDATES:{parts}")
        self._log(f"Candidates emitted: {len(deduped)}")

    def _emit_hunt_roi(self):
        """Emit SHOW_HUNT_ROI with logical CSS coordinates so Electron draws the red outline."""
        cb = self.cursor_bounds
        w = cb['width']
        h = cb['height']
        # Hunt window in physical capture px → convert to logical cursor px
        hx1 = int(self.hunt_left   / self.scale)
        hy1 = int(self.hunt_top    / self.scale)
        hx2 = int((w * self.scale - self.hunt_right)  / self.scale)
        hy2 = int((h * self.scale - self.hunt_bottom) / self.scale)
        # Absolute screen coordinates (logical)
        ax1 = cb['x'] + hx1
        ay1 = cb['y'] + hy1
        ax2 = cb['x'] + hx2
        ay2 = cb['y'] + hy2
        self._emit(f"SHOW_HUNT_ROI:{ax1},{ay1},{ax2},{ay2}")
        self._log(f"Hunt ROI (logical): ({ax1},{ay1})-({ax2},{ay2})  margins: L={self.hunt_left} T={self.hunt_top} R={self.hunt_right} B={self.hunt_bottom}")

    def _load_gather_ui_tpl(self):
        """Loading gather-UI template (dobicha.png)."""
        p = GATHER_UI_TPL
        if os.path.exists(p):
            img = cv2.imread(p)
            if img is not None:
                self._gather_ui_tpl = img
                self._log(f"Gather-UI template loaded: {p} {img.shape[1]}x{img.shape[0]}")
                return
        self._log(f"WARNING: {p} not found — diff method disabled")

    def _load_gather_banner_tpl(self):
        """Loading gather-banner template (banner.png)."""
        p = GATHER_BANNER_TPL
        if os.path.exists(p):
            img = cv2.imread(p)
            if img is not None:
                self._gather_banner_tpl = img
                self._log(f"Gather-banner template loaded: {p} {img.shape[1]}x{img.shape[0]}")
                return
        self._log(f"WARNING: {p} not found — banner check disabled")

    def _load_proverka_tpl(self):
        """Loading inspection template (proverka.png)."""
        p = PROVERKA_TPL
        if os.path.exists(p):
            img = cv2.imread(p)
            if img is not None:
                self._proverka_tpl = img
                self._log(f"Proverka template loaded: {p} {img.shape[1]}x{img.shape[0]}")
                return
        self._log(f"WARNING: {p} not found — inspection monitor disabled")

    def _load_neudacha_tpl(self):
        """Loading neudacha template (neudacha.png)."""
        p = NEUDACHA_TPL
        if os.path.exists(p):
            img = cv2.imread(p)
            if img is not None:
                self._neudacha_tpl = img
                self._log(f"Neudacha template loaded: {p} {img.shape[1]}x{img.shape[0]}")
                return
        self._log(f"WARNING: {p} not found — neudacha monitor disabled")

    def _load_boi_tpl(self):
        """Loading boi template (boi.png) — останавливает весь поиск пока видно."""
        p = BOI_TPL
        if os.path.exists(p):
            img = cv2.imread(p)
            if img is not None:
                self._boi_tpl = img
                self._log(f"Boi template loaded: {p} {img.shape[1]}x{img.shape[0]}")
                return
        self._log(f"WARNING: {p} not found — boi monitor disabled")

    def _load_block_tpl(self):
        """Loading block template (block.png) — окно нападения, останавливает поиск."""
        p = BLOCK_TPL
        if os.path.exists(p):
            img = cv2.imread(p)
            if img is not None:
                self._block_tpl = img
                self._log(f"Block template loaded: {p} {img.shape[1]}x{img.shape[0]}")
                return
        self._log(f"WARNING: {p} not found — block monitor disabled")


    def _boi_monitor_loop(self):
        """Фоновый тред: следит за boi.png и block.png.
        Пока любое из окон видно — выставляет _boi_active=True (скролл и поиск останавливаются).
        После исчезновения обоих — сбрасывает флаг и очищает dead_zones для чистого старта.
        """
        self._log("Boi/Block monitor started")
        while self.running:
            time.sleep(BOI_CHECK_INTERVAL)
            if not self.running:
                break

            shot = self._grab_screenshot()
            if shot is None:
                continue
            sh, sw = shot.shape[:2]

            def _check_tpl(tpl, thresh):
                if tpl is None:
                    return False
                th, tw = tpl.shape[:2]
                if tw > sw or th > sh:
                    return False
                try:
                    res = cv2.matchTemplate(shot, tpl, cv2.TM_CCOEFF_NORMED)
                    _, max_val, _, _ = cv2.minMaxLoc(res)
                    return max_val >= thresh
                except cv2.error:
                    return False

            boi_seen   = _check_tpl(self._boi_tpl,   BOI_THRESH)
            block_seen = _check_tpl(self._block_tpl,  BLOCK_THRESH)
            combat     = boi_seen or block_seen

            if combat:
                if not self._boi_active:
                    reason = "BLOCK" if block_seen else "BOI"
                    self._boi_active = True
                    self._log(f"{reason} detected — pausing search")
                    self._emit("BOI_DETECTED")
            else:
                if self._boi_active:
                    self._boi_active = False
                    self._no_match_streak    = 0
                    self._scroll_steps_down  = 0
                    self._dead_zones         = []
                    self._clicked_recently   = []
                    self._color_reject_zones = []
                    self._log("Combat gone — resuming search (dead zones cleared)")
                    self._emit("BOI_GONE")
        self._log("Boi/Block monitor stopped")

    def _neudacha_monitor_loop(self):
        """Фоновый тред: проверяет наличие окна neudacha.png.
        При обнаружении — кликает кнопку «Закрыть» и продолжает поиск ресурсов.
        """
        self._log("Neudacha monitor started")
        while self.running:
            time.sleep(NEUDACHA_CHECK_INTERVAL)
            if not self.running:
                break
            if self._neudacha_tpl is None or self._neudacha_closing:
                continue
            shot = self._grab_screenshot()
            if shot is None:
                continue
            tpl = self._neudacha_tpl
            th, tw = tpl.shape[:2]
            sh, sw = shot.shape[:2]
            if tw > sw or th > sh:
                continue
            try:
                res = cv2.matchTemplate(shot, tpl, cv2.TM_CCOEFF_NORMED)
                _, max_val, _, max_loc = cv2.minMaxLoc(res)
            except cv2.error:
                continue

            if max_val >= NEUDACHA_THRESH:
                self._log(f"NEUDACHA detected (conf={max_val:.3f}) @ {max_loc} — closing window")
                self._emit("NEUDACHA_DETECTED")
                self._neudacha_closing = True
                try:
                    # Сохраняем debug-скриншот с отметкой места клика
                    try:
                        os.makedirs('debug', exist_ok=True)
                        dbg = shot.copy()
                        tpl_h, tpl_w = tpl.shape[:2]
                        cv2.rectangle(dbg, max_loc,
                                      (max_loc[0] + tpl_w, max_loc[1] + tpl_h),
                                      (0, 255, 255), 2)
                        close_cap_x = max_loc[0] + NEUDACHA_CLOSE_OFFSET_X
                        close_cap_y = max_loc[1] + NEUDACHA_CLOSE_OFFSET_Y
                        cv2.circle(dbg, (close_cap_x, close_cap_y), 10, (0, 0, 255), -1)
                        cv2.putText(dbg, 'CLICK', (close_cap_x - 20, close_cap_y - 14),
                                    cv2.FONT_HERSHEY_SIMPLEX, 0.6, (0, 0, 255), 2)
                        cv2.imwrite(f'debug/neudacha_{int(time.time())}.png', dbg)
                    except Exception:
                        pass

                    # Координаты кнопки закрыть
                    close_cap_x = max_loc[0] + NEUDACHA_CLOSE_OFFSET_X
                    close_cap_y = max_loc[1] + NEUDACHA_CLOSE_OFFSET_Y
                    close_scr_x = int(self.cursor_bounds['x'] + close_cap_x / self.scale)
                    close_scr_y = int(self.cursor_bounds['y'] + close_cap_y / self.scale)
                    self._log(f"Clicking close btn at capture=({close_cap_x},{close_cap_y}) screen=({close_scr_x},{close_scr_y})")
                    self._move_to(close_scr_x, close_scr_y, duration=0.1)
                    time.sleep(0.15)
                    self._click()
                    time.sleep(0.5)
                    self._log("Neudacha window closed — resuming")
                    self._emit("NEUDACHA_CLOSED")
                    self._neudacha_closing = False
                except Exception as e:
                    self._log(f"Neudacha close error: {e}")
                    self._neudacha_closing = False
            # Если окно ушло — ничего не делаем (флаг уже сброшен)
        self._log("Neudacha monitor stopped")

    def _beep(self):
        """Sharp beep sound (Windows Beep)."""
        try:
            winsound.Beep(PROVERKA_BEEP_HZ, PROVERKA_BEEP_MS)
        except Exception:
            pass

    def _proverka_monitor_loop(self):
        """Background thread: periodically checks for proverka.png and beeps."""
        self._log("Proverka monitor started")
        while self.running:
            time.sleep(PROVERKA_CHECK_INTERVAL)
            if not self.running:
                break
            if self._proverka_tpl is None:
                continue
            shot = self._grab_screenshot()
            if shot is None:
                continue
            tpl = self._proverka_tpl
            th, tw = tpl.shape[:2]
            sh, sw = shot.shape[:2]
            if tw > sw or th > sh:
                continue
            try:
                res = cv2.matchTemplate(shot, tpl, cv2.TM_CCOEFF_NORMED)
                _, max_val, _, _ = cv2.minMaxLoc(res)
            except cv2.error:
                continue

            if max_val >= PROVERKA_THRESH:
                if not self._proverka_alerted:
                    self._log(f"!!! PROVERKA detected (conf={max_val:.3f}) — BEEP !!!")
                    self._emit("PROVERKA_DETECTED")
                    # Three sharp beeps in a separate thread to avoid blocking
                    threading.Thread(target=self._beep_alarm, daemon=True).start()
                    self._proverka_alerted = True
            else:
                # Window gone — reset flag so we beep again next time it appears
                self._proverka_alerted = False
        self._log("Proverka monitor stopped")

    def _beep_alarm(self):
        """Three sharp beeps in a row."""
        for _ in range(3):
            try:
                winsound.Beep(PROVERKA_BEEP_HZ, PROVERKA_BEEP_MS)
            except Exception:
                pass
            time.sleep(0.15)

    # ── sample loading ──────────────────────────────────────────────────────────

    def load_samples(self):
        raw = []

        # 1) training_data/vkusnocvet/ — основная папка с сэмплами вкусноцвета
        vkusn_dir = os.path.join('training_data', 'vkusnocvet')
        if os.path.isdir(vkusn_dir):
            def _vkey(n):
                base = os.path.splitext(n)[0]
                num = base.split('_')[-1]
                return int(num) if num.isdigit() else 0
            vkusn_files = sorted([f for f in os.listdir(vkusn_dir)
                                   if f.endswith('.png')], key=_vkey)
            for i, fname in enumerate(vkusn_files):
                p = os.path.join(vkusn_dir, fname)
                img = cv2.imread(p)
                if img is not None:
                    h, w = img.shape[:2]
                    raw.append({'x': (i + 1) * 200, 'y': 1, 'image': p,
                                'width': w, 'height': h, 'label': 'vkusnocvet'})
            self._log(f"Loaded {len(vkusn_files)} templates from training_data/vkusnocvet/ (vkusnocvet)")

        # 1b) templates/ folder — fallback если вдруг там ещё есть файлы
        # (после normalize_samples.py все файлы переехали в training_data/vkusnocvet/)
        if not raw:
            tpl_files = sorted(glob.glob('templates/template_*.png'),
                               key=lambda n: int(n.split('_')[-1].split('.')[0]))
            for i, p in enumerate(tpl_files):
                img = cv2.imread(p)
                if img is not None:
                    h, w = img.shape[:2]
                    raw.append({'x': (i + 1) * 200, 'y': 1, 'image': p, 'width': w, 'height': h,
                                'label': 'vkusnocvet'})
            if tpl_files:
                self._log(f"Loaded {len(tpl_files)} templates from templates/ (vkusnocvet fallback)")

        # 1c) povei_pattern.png — отдельный шаблон повея если есть
        if os.path.exists('povei_pattern.png'):
            img = cv2.imread('povei_pattern.png')
            if img is not None:
                h, w = img.shape[:2]
                raw.append({'x': 9000, 'y': 1, 'image': 'povei_pattern.png',
                            'width': w, 'height': h, 'label': 'povei'})
                self._log("Loaded povei_pattern.png as template (povei)")

        # 2) training_data/povei/ — отдельная папка для повея
        povei_dir = os.path.join('training_data', 'povei')
        if os.path.isdir(povei_dir):
            def _key(n):
                base = os.path.splitext(n)[0]
                num = base.split('_')[-1]
                return int(num) if num.isdigit() else 0
            povei_files = sorted([f for f in os.listdir(povei_dir)
                                   if f.endswith('.png')], key=_key)
            offset = len(raw)
            for i, fname in enumerate(povei_files):
                p = os.path.join(povei_dir, fname)
                img = cv2.imread(p)
                if img is not None:
                    h, w = img.shape[:2]
                    raw.append({'x': (offset + i + 1) * 200, 'y': 2, 'image': p,
                                'width': w, 'height': h, 'label': 'povei'})
            self._log(f"Loaded {len(povei_files)} templates from training_data/povei/ (povei)")

        # 3) Always merge recorded_samples.json — add any entries not already covered
        if os.path.exists('recorded_samples.json'):
            try:
                with open('recorded_samples.json', 'r', encoding='utf-8') as f:
                    json_entries = json.load(f)
                # Collect paths already loaded above (to avoid duplicates)
                loaded_paths = {os.path.normpath(e['image']) for e in raw}
                extra = []
                for e in json_entries:
                    p = e.get('image', '')
                    if not p:
                        continue
                    norm = os.path.normpath(p)
                    if norm not in loaded_paths and os.path.exists(p):
                        extra.append(e)
                        loaded_paths.add(norm)
                if extra:
                    self._log(f"Merged {len(extra)} extra entries from recorded_samples.json")
                    raw.extend(extra)
            except Exception as e:
                self._log(f"Error reading recorded_samples.json: {e}")

        if raw:
            self._log(f"Total templates to load: {len(raw)}")
            self._build_template_cache(raw)
            return

        # 4) Fallback: training_data/ root samples
        td = 'training_data'
        if os.path.isdir(td):
            def key(n):
                p = n.split('_')[1].split('.')[0]
                return int(p) if p.isdigit() else 0
            files = sorted([f for f in os.listdir(td)
                            if f.startswith('sample_') and f.endswith('.png')], key=key)
            raw = []
            for fname in files:
                p = os.path.join(td, fname)
                img = cv2.imread(p)
                if img is not None:
                    h, w = img.shape[:2]
                    raw.append({'x': 0, 'y': 0, 'image': p, 'width': w, 'height': h})
            self._log(f"Fallback: loaded {len(raw)} samples from training_data/")
            self._build_template_cache(raw)
        else:
            self._log("No samples found. Use RECORD mode or run make_templates.py")

    def _build_template_cache(self, raw_samples):
        self.recorded_samples = []
        self.sample_templates = []
        skipped = 0
        for s in raw_samples:
            p = s.get('image', '')
            if not p or not os.path.exists(p):
                skipped += 1
                continue
            img = cv2.imread(p)
            if img is None:
                skipped += 1
                continue
            self.recorded_samples.append(s)
            self.sample_templates.append(img)
        if skipped:
            self._log(f"Skipped {skipped} broken/missing samples")
        self._log(f"Template cache ready: {len(self.sample_templates)} templates")

        # Dedup: from similar templates (same position ±5px) keep one
        self._dedupe_templates()

        if skipped:
            try:
                with open('recorded_samples.json', 'w', encoding='utf-8') as f:
                    json.dump(self.recorded_samples, f, indent=2, ensure_ascii=False)
                self._log("recorded_samples.json sanitized")
            except Exception as e:
                self._log(f"Could not rewrite recorded_samples.json: {e}")

    def _dedupe_templates(self):
        """
        Filter and deduplication.
        For file-based templates (label set, x/y are synthetic indices) — skip position filter,
        just deduplicate by image hash to remove pixel-identical duplicates.
        For recorded samples (x=0,y=0 or real coords) — use position filter.
        """
        if not self.recorded_samples:
            return
        orig = len(self.sample_templates)

        keep_idx   = []
        seen_hashes = set()
        seen_positions = []

        for i, s in enumerate(self.recorded_samples):
            x, y  = s.get('x', 0), s.get('y', 0)
            label = s.get('label', '')

            # File-based templates have label set — deduplicate by image hash only
            if label in ('vkusnocvet', 'povei', 'recorded'):
                tpl = self.sample_templates[i]
                h = hash(tpl.tobytes())
                if h not in seen_hashes:
                    seen_hashes.add(h)
                    keep_idx.append(i)
                continue

            # Recorded samples without label — filter by image hash + position
            if x == 0 and y == 0:
                continue
            # Check image hash first (skip exact duplicates regardless of position)
            tpl = self.sample_templates[i]
            img_h = hash(tpl.tobytes())
            if img_h in seen_hashes:
                continue
            # Position dedup — keep one per ~10px zone
            dup = any(abs(x - sx) < 10 and abs(y - sy) < 10 for sx, sy in seen_positions)
            if not dup:
                seen_hashes.add(img_h)
                keep_idx.append(i)
                seen_positions.append((x, y))

        self.recorded_samples = [self.recorded_samples[i] for i in keep_idx]
        self.sample_templates  = [self.sample_templates[i]  for i in keep_idx]
        self._log(f"After dedup: {orig} -> {len(self.sample_templates)} templates")
        self._tpl_cache = []
        self._build_enhanced_templates()

    # ── stdin stop listener ─────────────────────────────────────────────────────

    def _stdin_stop_listener(self):
        """
        Read stdin line by line via readline() — not buffered,
        each line arrives immediately as Electron sends it.
        EOF (stdin.end() from Electron) also triggers stop.
        Supported commands:
          CMD_STOP [token]
          CMD_SET_HUNT_ROI left,top,right,bottom
        """
        try:
            while True:
                line = sys.stdin.readline()
                if line == '':          # EOF — stdin closed by Electron
                    # DO NOT stop the bot on EOF — Electron may close the pipe
                    # during network hiccups (ERR_NETWORK_CHANGED) without intending
                    # to stop the bot.  Just wait for an explicit CMD_STOP instead.
                    self._log("stdin EOF — pipe closed, but continuing (waiting for CMD_STOP or F8)")
                    # Wait a bit then exit the thread — bot keeps running
                    time.sleep(2)
                    break
                cmd = line.strip()
                if not cmd:
                    continue

                # ── CMD_SET_HUNT_ROI left,top,right,bottom ──────────────────────
                if cmd.startswith('CMD_SET_HUNT_ROI'):
                    try:
                        parts = cmd.split(' ', 1)
                        vals = [int(v.strip()) for v in parts[1].split(',')]
                        if len(vals) == 4:
                            self.hunt_left, self.hunt_top, self.hunt_right, self.hunt_bottom = vals
                            self._log(f"Hunt ROI updated: L={self.hunt_left} T={self.hunt_top} R={self.hunt_right} B={self.hunt_bottom}")
                            self._emit_hunt_roi()
                    except Exception as e:
                        self._log(f"CMD_SET_HUNT_ROI parse error: {e}")
                    continue


                # ── CMD_HINT_POVEI x,y — обратная совместимость ──────────────
                if cmd.startswith('CMD_HINT_POVEI'):
                    try:
                        parts = cmd.split(' ', 1)
                        vals = [int(v.strip()) for v in parts[1].split(',')]
                        if len(vals) == 2:
                            hx, hy = vals
                            threading.Thread(
                                target=self._hint_save, args=('povei', hx, hy), daemon=True
                            ).start()
                    except Exception as e:
                        self._log(f"CMD_HINT_POVEI parse error: {e}")
                    continue

                # ── CMD_SCAN_POVEI — скан повея на ходу (бот запущен) ────────
                if cmd == 'CMD_SCAN_POVEI':
                    threading.Thread(target=self.scan_povei_once, daemon=True).start()
                    continue
                if cmd.startswith('CMD_HINT '):
                    try:
                        parts = cmd.split(' ', 2)  # ['CMD_HINT', 'povei', 'x,y']
                        hlabel = parts[1].strip()
                        vals = [int(v.strip()) for v in parts[2].split(',')]
                        if len(vals) == 2 and hlabel in ('povei', 'vkusnocvet'):
                            hx, hy = vals
                            threading.Thread(
                                target=self._hint_save, args=(hlabel, hx, hy), daemon=True
                            ).start()
                    except Exception as e:
                        self._log(f"CMD_HINT parse error: {e}")
                    continue

                if not cmd.startswith('CMD_STOP'):
                    continue
                parts = cmd.split(' ', 1)
                incoming = parts[1].strip() if len(parts) > 1 else ''
                if self.stop_token and incoming != self.stop_token:
                    self._log("Wrong stop token, ignoring")
                    continue
                self._log("STOP command received — stopping...")
                self.running = False
                if self.record_mode and not self._saved_on_exit:
                    self.save_all_samples()
                    self._saved_on_exit = True
                break
        except Exception as e:
            self._log(f"stdin listener error: {e}")
            self.running = False

    def _sleep(self, seconds):
        """Interruptible sleep — checks self.running every 0.2 sec."""
        deadline = time.time() + seconds
        while self.running and time.time() < deadline:
            time.sleep(0.2)

    def _hint_save(self, label, px, py):
        """
        Сохраняет сэмпл ресурса на ходу — как Live-Marker но во время работы бота.
        БЕЗ движения курсора — мгновенный скриншот текущего состояния экрана.
        Добавляет шаблон в _tpl_cache сразу.

        label: 'povei' или 'vkusnocvet'
        px, py: физические px в capture-области
        """
        self._log(f"[hint] Saving {label} sample at ({px},{py})")
        self._emit(f"SHOW_SQUARE:{px},{py},{label}")

        # Мгновенный скриншот — без движения курсора, без паузы
        shot = self._grab_screenshot()
        if shot is None:
            self._log(f"[hint] ERROR: could not grab screenshot")
            return

        save_dir = os.path.join('training_data', label)
        os.makedirs(save_dir, exist_ok=True)

        half = POVEI_CROP_HALF if label == 'povei' else CROP_HALF
        x1 = max(0, px - half)
        y1 = max(0, py - half)
        x2 = min(shot.shape[1], px + half)
        y2 = min(shot.shape[0], py + half)
        crop = shot[y1:y2, x1:x2]
        if crop.size == 0:
            self._log(f"[hint] ERROR: empty crop")
            return

        # Уникальное имя файла
        existing = [f for f in os.listdir(save_dir) if f.endswith('.png')]
        nums = [int(os.path.splitext(f)[0].split('_')[-1])
                for f in existing if os.path.splitext(f)[0].split('_')[-1].isdigit()]
        next_id = (max(nums) + 1) if nums else 0
        path = os.path.join(save_dir, f"sample_{next_id}.png").replace('\\', '/')
        cv2.imwrite(path, crop)

        # Добавляем в кэш немедленно — бот сразу начнёт находить этот ресурс
        mask = self._make_fg_mask(crop)
        gray_eq, hue, edges = self._preprocess(crop)
        entry = {'x': px, 'y': py, 'image': path,
                 'width': x2 - x1, 'height': y2 - y1, 'label': label}
        self.recorded_samples.append(entry)
        self.sample_templates.append(crop.copy())
        self._tpl_cache.append({
            'bgr':   crop,
            'gray':  gray_eq,
            'hue':   cv2.bitwise_and(hue, hue, mask=mask),
            'edges': cv2.bitwise_and(edges, edges, mask=mask),
            'mask':  mask,
            'label': label,
            'image': path,
        })
        n_label = sum(1 for tc in self._tpl_cache if tc['label'] == label)
        self._log(f"[hint] Saved {path}  {label}_templates={n_label}  cache={len(self._tpl_cache)}")
        self._emit(f"HINT_SAVED:{label},{n_label}")
        # Сохраняем превью в debug/
        try:
            os.makedirs('debug', exist_ok=True)
            preview = crop.copy()
            cv2.putText(preview, label, (2, 14),
                        cv2.FONT_HERSHEY_SIMPLEX, 0.5,
                        (0, 255, 0) if label == 'povei' else (255, 0, 255), 1)
            cv2.imwrite(f'debug/hint_{label}_{next_id}.png', preview)
        except Exception:
            pass
        # Подсветить место ещё раз после сохранения
        self._emit(f"SHOW_SQUARE:{px},{py},{label}")

    # обратная совместимость
    def _hint_save_povei(self, px, py):
        self._hint_save('povei', px, py)

    # ── main entry point ────────────────────────────────────────────────────────

    def start(self):
        t = threading.Thread(target=self._stdin_stop_listener, daemon=True)
        t.start()

        if self.record_mode:
            self._log("=== RECORD MODE === Click on hunt resources in the game window")
            self.start_recording()
        else:
            if not self.sample_templates:
                self._log("ERROR: No templates loaded. Run RECORD mode first.")
                return
            self._log(f"=== AUTO MODE === {len(self.sample_templates)} templates, threshold={MATCH_THRESHOLD}")
            self.running = True
            self._init_sweep()
            # Emit hunt window ROI so Electron can draw permanent red outline
            self._emit_hunt_roi()
            # Start background inspection monitor
            if self._proverka_tpl is not None:
                pm = threading.Thread(target=self._proverka_monitor_loop, daemon=True)
                pm.start()
            # Start neudacha monitor — auto-closes failure window
            if self._neudacha_tpl is not None:
                nm = threading.Thread(target=self._neudacha_monitor_loop, daemon=True)
                nm.start()
            # Start boi/block monitor — паузирует поиск пока видно окно боя или нападения
            if self._boi_tpl is not None or self._block_tpl is not None:
                bm = threading.Thread(target=self._boi_monitor_loop, daemon=True)
                bm.start()
            self._run_auto()

    # ── AUTO MODE ───────────────────────────────────────────────────────────────

    def _run_auto(self):
        while self.running:
            self._cycle_index += 1
            self._log(f"--- CYCLE #{self._cycle_index}  resources={self.resources_gathered} ---")
            self.auto_cycle()
            if self.max_cycles > 0 and self._cycle_index >= self.max_cycles:
                self._log(f"Reached max_cycles={self.max_cycles}, stopping")
                break
            if self.running:
                self._sleep(CYCLE_SLEEP)
        self._log(f"Bot stopped. Total resources: {self.resources_gathered}")

    def auto_cycle(self):
        # Если окно боя активно — пропускаем поиск полностью
        if self._boi_active:
            self._log("BOI active — search paused")
            self._emit("HIDE_SQUARE")
            self._emit("HIDE_CANDIDATES")
            return

        # Убираем любой висящий квадрат от предыдущего цикла
        self._emit("HIDE_SQUARE")

        now = time.time()
        # Purge expired cooldown entries
        self._clicked_recently = [
            (cx, cy, ts) for cx, cy, ts in self._clicked_recently
            if now - ts < CLICK_COOLDOWN
        ]
        # Purge expired dead-zones
        self._dead_zones = [
            (dx, dy, ts) for dx, dy, ts in self._dead_zones
            if now - ts < DEAD_COOLDOWN
        ]
        # Purge expired color-reject zones
        self._color_reject_zones = [
            (dx, dy, ts) for dx, dy, ts in self._color_reject_zones
            if now - ts < COLOR_REJECT_COOLDOWN
        ]

        screenshot = self._grab_screenshot()
        if screenshot is None:
            self._log("Screenshot failed, skipping cycle")
            return

        exclude = self._clicked_recently + self._dead_zones

        # Всегда показываем кандидатов в начале цикла — чтобы пользователь видел что видит бот
        self._emit_candidates(screenshot, exclude_pos=exclude)

        # ── Priority 1 (early): color-blob detection (vkusnocvet) — ДО повея ────
        # Вкусноцвет проверяется ПЕРВЫМ — если есть хотя бы один свободный вкусноцвет,
        # он важнее повея (занятого или свободного), т.к. добыча эффективнее.
        cblobs = self.find_color_blobs(screenshot, exclude)

        # ── Priority 0: повей — template matching внутри hunt window ─────────
        # Берём повей ТОЛЬКО если свободных вкусноцветов нет.
        if not cblobs:
            ppos, pconf = self.find_povei_match(screenshot, exclude, self._color_reject_zones)
            if ppos is not None:
                # Проверяем занятость — если ресурс уже добывается другим игроком, пропускаем
                if self._is_occupied(screenshot, ppos[0], ppos[1]):
                    self._log(f"POVEI target occupied at {ppos} — adding to dead_zones")
                    self._dead_zones.append((ppos[0], ppos[1], time.time()))
                else:
                    tidx = next((i for i,tc in enumerate(self._tpl_cache) if tc.get('label')=='povei'), -1)
                    self._log(f"POVEI target: conf={pconf:.3f} pos={ppos}")
                    self._no_match_streak   = 0
                    self._scroll_steps_down = 0
                    self._do_gather(ppos, pconf, tidx)
                    return

            # ── Priority 0b: повей — цветовой детектор (только если нет вкусноцвета) ──
            pblobs = self.find_povei_color_blobs(screenshot, exclude)
            if pblobs:
                bx, by, bscore = pblobs[0]
                # Cross-check: if this blob position has a LOT of vkusnocvet purple pixels,
                # it's likely part of a vkusnocvet flower, not a separate povei.
                pv1 = max(0, bx - 36); pv2 = min(screenshot.shape[1], bx + 36)
                ph1 = max(0, by - 36); ph2 = min(screenshot.shape[0], by + 36)
                p_patch_hsv = cv2.cvtColor(screenshot[ph1:ph2, pv1:pv2], cv2.COLOR_BGR2HSV)
                p_h, p_s, _ = cv2.split(p_patch_hsv)
                vkusn_px_at_povei = int(np.sum((p_h >= COLOR_H_LO) & (p_h <= COLOR_H_HI) & (p_s >= COLOR_S_MIN)))
                if vkusn_px_at_povei >= COLOR_MIN_PIXELS * 3:
                    self._log(f"POVEI-COLOR ({bx},{by}) skipped — strong vkusnocvet overlap (vkusn_px={vkusn_px_at_povei})")
                    pblobs = pblobs[1:]
                if pblobs:
                    bx, by, bscore = pblobs[0]
                    # Проверяем занятость повея-цвета перед кликом
                    if self._is_occupied(screenshot, bx, by):
                        self._log(f"POVEI-COLOR ({bx},{by}) occupied — adding to dead_zones")
                        self._dead_zones.append((bx, by, time.time()))
                    else:
                        tidx = next((i for i, tc in enumerate(self._tpl_cache) if tc.get('label') == 'povei'), -1)
                        self._log(f"POVEI-COLOR target: ({bx},{by}) score={bscore}")
                        self._no_match_streak   = 0
                        self._scroll_steps_down = 0
                        self._do_gather((bx, by), min(0.99, bscore / 30.0), tidx)
                        return
        else:
            self._log(f"Vkusnocvet blobs found ({len(cblobs)}) — skipping povei search")

        # ── Priority 1: color-blob detection (vkusnocvet purple/crimson) ──────
        if cblobs:
            bx, by, barea = cblobs[0]
            self._log(f"COLOR target: ({bx},{by}) area={barea}")
            self._no_match_streak   = 0
            self._scroll_steps_down = 0
            self._do_gather((bx, by), 0.0, -1)
            return

        # ── Priority 2: vkusnocvet template matching ──────────────────────────
        # Запускаем только если color blobs ничего не нашли (они быстрее)
        pos, conf, tidx = self.find_vkusn_match(screenshot, exclude)

        if conf >= MATCH_THRESHOLD and pos is not None:
            self._no_match_streak   = 0
            self._scroll_steps_down = 0
            self._do_gather(pos, conf, tidx)
            return

        self._log(f"No match (povei=0, color=0, template={conf:.3f})")
        self._no_match_streak += 1
        # Only scroll when no resources visible at all (neither color blobs nor povei blobs)
        povei_visible = bool(self.find_povei_color_blobs(screenshot, exclude))
        vkusn_visible = bool(self.find_color_blobs(screenshot, exclude))
        if not povei_visible and not vkusn_visible:
            self._try_scroll()
        else:
            self._log("Skip scroll — resources visible (povei or vkusnocvet color blobs found)")

    def _do_gather(self, pos, conf, tidx):
        """
        1. Move to target, double-click
        2. Poll for dobicha.png UI window
        3. On confirm — count resource; on timeout — dead-zone
        Uses GATHER_WAIT_POVEI for povei label (2 sec longer cooldown).

        Координаты:
          pos (lx, ly) — физические пиксели в capture-области (от mss)
          gx, gy       — экранные (screen) пиксели для SetCursorPos / pyautogui
          scale        — DPI scale factor (физ px / логич px)
        """
        lx, ly = pos
        gx = int(self.cursor_bounds['x'] + lx / self.scale)
        gy = int(self.cursor_bounds['y'] + ly / self.scale)
        # blob из color detector → сразу считаем вкусноцветом (тип фиксируется навсегда)
        raw_label = self._tpl_cache[tidx]['label'] if (self._tpl_cache and 0 <= tidx < len(self._tpl_cache)) else 'blob'
        label = 'vkusnocvet' if raw_label == 'blob' else raw_label
        gather_wait = GATHER_WAIT_POVEI if label == 'povei' else GATHER_WAIT
        conf_pct = min(99, int(conf * 100)) if conf > 0 else 0
        self._log(f"CANDIDATE conf={conf_pct}% [{label}] local=({lx},{ly}) global=({gx},{gy}) wait={gather_wait:.0f}s")
        # show_label: povei=зелёный, vkusnocvet=пурпурный (blob уже переименован выше)
        show_label = label if label in ('povei', 'vkusnocvet') else 'Match'
        if conf_pct > 0:
            self._emit(f"SHOW_SQUARE:{lx},{ly},{show_label}_{conf_pct}")
        else:
            self._emit(f"SHOW_SQUARE:{lx},{ly},{show_label}")

        # Снимаем скриншот ДО движения курсора — чистый вид без прицела предыдущего клика
        pre_click_shot = self._grab_screenshot()

        self._move_to(gx, gy, duration=0.2)
        self._sleep(0.15)
        if not self.running:
            self._emit("HIDE_SQUARE")
            return


        # Double-click the target
        self._emit("HIDE_CANDIDATES")
        self._dbl_click()
        click_ts = time.time()
        self._clicked_recently.append((lx, ly, click_ts))
        self._last_click_gx = gx
        self._last_click_gy = gy
        # Сбрасываем счётчики и эталон предыдущей добычи
        self._color_gone_consec = 0
        self._gather_ref_patch  = None
        self._gather_ref_res_px = 0
        self._bg_candidates     = []  # сбрасываем кэш кандидатов от прошлой добычи
        # Отводим курсор от ресурса сразу после клика — чтобы он не мешал color-check
        self._move_cursor_away()
        self._log(f"Clicking [{label}] ({lx},{ly}), wait {gather_wait:.0f}s...")
        self._emit("HIDE_SQUARE")

        # Poll dobicha.png every GATHER_CHECK_INTERVAL seconds.
        # Early exit: if dobicha not seen within GATHER_EARLY_MISS_SECS → dead-zone, find next.
        # Require GATHER_CONFIRM_HITS consecutive hits to confirm real gathering.
        # After confirm: watch pixels inside resource ring — ESC only when they disappear.
        consecutive_hits   = 0
        confirmed          = False
        dobicha_ts         = None
        consec_miss_after  = 0   # consecutive misses AFTER confirmation
        ref_set            = False   # True когда live-эталон цвета снят (через GATHER_REF_DELAY_SECS)
        _bg_scroll_grace_until = 0.0  # after BG scroll: ignore misses until this timestamp
        early_miss_deadline = time.time() + GATHER_EARLY_MISS_SECS
        deadline            = time.time() + gather_wait
        _last_bg_scroll_ts  = time.time()
        _last_banner_check_ts = time.time()  # время последней проверки banner.png

        while self.running and time.time() < deadline:
            # ── Пауза при бое/нападении ───────────────────────────────────────
            if self._boi_active:
                self._log("BOI/BLOCK active — gather loop paused")
                while self.running and self._boi_active:
                    self._sleep(1.0)
                if not self.running:
                    return
                self._log("BOI/BLOCK gone — gather loop resumed")
                # Сразу проверяем баннер — ресурс мог смениться за время боя
                resume_shot = self._grab_screenshot()
                if not self._check_banner_only(resume_shot):
                    self._log("Banner absent after combat — jumping to next resource")
                    self._emit("HIDE_SQUARE")
                    self._emit("HIDE_CANDIDATES")
                    self._press_esc()
                    self._sleep(0.3)
                    self._search_and_gather_next()
                    return
                # Баннер есть — продолжаем добычу, продлеваем дедлайн
                deadline = time.time() + gather_wait
                _last_banner_check_ts = time.time()
                confirmed = True  # раз баннер есть — добыча точно подтверждена

            self._sleep(GATHER_CHECK_INTERVAL)
            if not self.running:
                return
            s       = self._grab_screenshot()
            hit     = self._check_gather_ui(s)
            elapsed = time.time() - click_ts

            if hit:
                consecutive_hits  += 1
                consec_miss_after  = 0

                # ── Подтверждение добычи ──────────────────────────────────────
                if consecutive_hits >= GATHER_CONFIRM_HITS and not confirmed:
                    confirmed  = True
                    dobicha_ts = time.time()
                    self._log(f"Gathering CONFIRMED [{label}] at +{elapsed:.0f}s")
                    self._emit(f"SHOW_SQUARE:{lx},{ly},gathering")
                    self._save_confirmed_sample(lx, ly, label, pre_shot=pre_click_shot)
                    if s is not None:
                        cand_exclude = self._clicked_recently + self._dead_zones
                        self._emit_candidates(s, exclude_pos=cand_exclude)

                # ── Снятие живого эталона через GATHER_REF_DELAY_SECS ──────────
                if confirmed and not ref_set and elapsed >= GATHER_REF_DELAY_SECS:
                    effective_label = label if label in ('vkusnocvet', 'povei') else 'vkusnocvet'
                    self._set_gather_ref(s, lx, ly, effective_label)
                    ref_set = True

                # ── Фоновый скролл пока добываем ──────────────────────────────
                if confirmed and not self.dry_run:
                    now_bg = time.time()
                    if now_bg - _last_bg_scroll_ts >= GATHER_SCAN_INTERVAL:
                        _last_bg_scroll_ts = now_bg
                        bg_shot = self._grab_screenshot()
                        if bg_shot is not None:
                            bg_exclude = self._clicked_recently + self._dead_zones
                            bg_vkusn = self.find_color_blobs(bg_shot, bg_exclude)
                            bg_povei = self.find_povei_color_blobs(bg_shot, bg_exclude)
                            bg_has_vkusn = bool(bg_vkusn)
                            bg_has_povei = bool(bg_povei)

                            # ── Сохраняем кандидатов найденных во время добычи ──
                            new_bg_candidates = []
                            for bx, by, barea in bg_vkusn:
                                new_bg_candidates.append((bx, by, 'vkusnocvet', barea))
                            for bx, by, bscore in bg_povei:
                                new_bg_candidates.append((bx, by, 'povei', bscore))
                            if new_bg_candidates:
                                self._bg_candidates = new_bg_candidates

                            if not bg_has_vkusn and not bg_has_povei:
                                self._bg_candidates = []
                                self._emit("HIDE_CANDIDATES")
                                self._emit("HIDE_SQUARE")  # скрываем квадрат — после скролла координаты устареют
                                bg_pos = getattr(self, '_scroll_pos', 0)
                                bg_dir = -1 if bg_pos >= SCROLL_CYCLE_STEPS else 1
                                self._scroll_silent(GATHER_SCAN_SCROLL * bg_dir, 1)
                                self._scroll_pos = (bg_pos + 1) % (SCROLL_CYCLE_STEPS * 2)
                                if bg_dir < 0:
                                    self._dead_zones       = []
                                    self._clicked_recently = []
                                self._color_reject_zones = []
                                self._log(f"BG scroll {'down' if bg_dir>0 else 'UP'} at +{elapsed:.0f}s")
                                _bg_scroll_grace_until = time.time() + 3.0
                                # Сбрасываем таймер проверки баннера — после скролла баннер
                                # может временно исчезнуть, не считать это концом добычи
                                _last_banner_check_ts = time.time() + GATHER_BANNER_CHECK_INTERVAL
                                post_bg = self._grab_screenshot()
                                if post_bg is not None:
                                    self._emit_candidates(post_bg, exclude_pos=self._clicked_recently + self._dead_zones)


            else:
                # dobicha MISS
                if confirmed:
                    # Grace-период после BG-скролла
                    if time.time() < _bg_scroll_grace_until:
                        consecutive_hits = max(0, consecutive_hits - 1)
                        continue

                    # Снимаем ref если ещё не снят
                    if not ref_set and s is not None:
                        effective_label = label if label in ('vkusnocvet', 'povei') else 'vkusnocvet'
                        self._set_gather_ref(s, lx, ly, effective_label)
                        ref_set = True

                    # Проверяем цвет — если ресурс ещё есть, игнорируем miss
                    if ref_set and s is not None:
                        effective_label = label if label in ('vkusnocvet', 'povei') else 'vkusnocvet'
                        ref_px = getattr(self, '_gather_ref_res_px', 0)
                        if ref_px > 0:
                            cur_px = self._count_resource_pixels_in_circle(s, lx, ly, effective_label)
                            threshold = max(2, int(ref_px * 0.15))
                            if cur_px >= threshold:
                                consecutive_hits = max(0, consecutive_hits - 1)
                                consec_miss_after = max(0, consec_miss_after - 1)
                                continue

                    consec_miss_after += 1
                    consecutive_hits = max(0, consecutive_hits - 1)
                    continue

                consecutive_hits = 0
                if not confirmed and time.time() > early_miss_deadline:
                    self._log(f"No dobicha in {GATHER_EARLY_MISS_SECS:.0f}s — dead-zone [{label}]")
                    self._emit(f"SHOW_SQUARE:{lx},{ly},Weak")
                    self._emit("HIDE_CANDIDATES")
                    self._dead_zones.append((lx, ly, time.time()))
                    if label in ('povei', 'vkusnocvet') and pre_click_shot is not None:
                        self._save_false_positive_sample(lx, ly, label, pre_click_shot)

            # ── Проверка banner каждые GATHER_BANNER_CHECK_INTERVAL сек ─────
            # Независимо от hit/miss: если баннер пропал — добыча закончилась
            if confirmed:
                now_bc = time.time()
                if now_bc - _last_banner_check_ts >= GATHER_BANNER_CHECK_INTERVAL:
                    _last_banner_check_ts = now_bc
                    banner_shot = self._grab_screenshot()
                    if not self._check_banner_only(banner_shot):
                        # Перепроверяем через 1 сек — исключаем ложный пропуск при скролле
                        self._sleep(1.0)
                        banner_shot2 = self._grab_screenshot()
                        if not self._check_banner_only(banner_shot2):
                            self._log(f"Banner GONE (confirmed 2x) at +{elapsed:.0f}s — jumping to next")
                            self.resources_gathered += 1
                            self._emit(f"RESOURCES:{self.resources_gathered}")
                            self._no_match_streak = 0
                            self._emit("HIDE_SQUARE")
                            self._emit("HIDE_CANDIDATES")
                            self._press_esc()
                            self._sleep(0.3)
                            self._search_and_gather_next()
                            return

        # ── Таймаут добычи ────────────────────────────────────────────────────
        if not self.running:
            return

        if confirmed:
            self.resources_gathered += 1
            self._emit(f"RESOURCES:{self.resources_gathered}")
            self._no_match_streak = 0
            self._log(f"Resource counted (timeout). Total: {self.resources_gathered}")
            self._emit("HIDE_SQUARE")
            self._emit("HIDE_CANDIDATES")
            self._press_esc()
            self._sleep(0.3)
            self._search_and_gather_next()
            return
        else:
            self._log(f"dobicha not confirmed after {gather_wait:.0f}s — false positive, dead-zone")
            self._emit(f"SHOW_SQUARE:{lx},{ly},Weak")
            self._dead_zones.append((lx, ly, time.time()))
            if label in ('povei', 'vkusnocvet') and pre_click_shot is not None:
                self._save_false_positive_sample(lx, ly, label, pre_click_shot)
            if not self.dry_run:
                check_shot  = self._grab_screenshot()
                exclude_now = self._clicked_recently + self._dead_zones
                if not self.find_color_blobs(check_shot, exclude_now) and \
                   not self.find_povei_color_blobs(check_shot, exclude_now):
                    self._no_match_streak += 1
                    self._try_scroll()
            self._search_and_gather_next()

    def _check_selection_circle(self, screenshot, cx, cy):
        """
        Search for selection circle around point (cx, cy) via HoughCircles.
        Strict: requires bright ring with high contrast vs darker interior.
        Saves debug ROI image when circle is confirmed.
        """
        if screenshot is None:
            return False

        h, w = screenshot.shape[:2]
        x1 = max(0, int(cx) - CIRCLE_SEARCH_R)
        y1 = max(0, int(cy) - CIRCLE_SEARCH_R)
        x2 = min(w, int(cx) + CIRCLE_SEARCH_R)
        y2 = min(h, int(cy) + CIRCLE_SEARCH_R)
        roi = screenshot[y1:y2, x1:x2]

        if roi.size == 0:
            return False

        gray = cv2.cvtColor(roi, cv2.COLOR_BGR2GRAY)
        blurred = cv2.GaussianBlur(gray, (5, 5), 1.5)

        roi_cx = (x2 - x1) // 2
        roi_cy = (y2 - y1) // 2
        bg_bright = float(np.mean(blurred))

        circles = cv2.HoughCircles(
            blurred,
            cv2.HOUGH_GRADIENT,
            dp=1.2,
            minDist=20,
            param1=60,
            param2=25,   # stricter — fewer false positives
            minRadius=CIRCLE_RADIUS_MIN,
            maxRadius=CIRCLE_RADIUS_MAX
        )

        if circles is None:
            self._log(f"Circle check: none found (bg={bg_bright:.1f})")
            return False

        circles = np.round(circles[0]).astype(int)
        candidates = []

        for (x, y, r) in circles:
            dist = float(np.sqrt((x - roi_cx) ** 2 + (y - roi_cy) ** 2))
            if dist > CIRCLE_SEARCH_R * 0.55:
                continue

            mask_ring = np.zeros(blurred.shape, dtype=np.uint8)
            cv2.circle(mask_ring, (x, y), r, 255, 3)
            ring_bright = cv2.mean(blurred, mask=mask_ring)[0]

            mask_inner = np.zeros(blurred.shape, dtype=np.uint8)
            cv2.circle(mask_inner, (x, y), max(1, r - 8), 255, -1)
            inner_bright = cv2.mean(blurred, mask=mask_inner)[0]

            contrast = ring_bright - inner_bright
            candidates.append((x, y, r, dist, ring_bright, inner_bright, contrast))
            self._log(f"Circle candidate: r={r} dist={dist:.1f} ring={ring_bright:.1f} inner={inner_bright:.1f} contrast={contrast:.1f}")

        for (x, y, r, dist, ring_bright, inner_bright, contrast) in candidates:
            if ring_bright >= CIRCLE_MIN_BRIGHT and contrast >= CIRCLE_MIN_CONTRAST:
                self._log(f"Circle CONFIRMED: r={r} dist={dist:.1f} contrast={contrast:.1f}")
                if CIRCLE_SAVE_DEBUG:
                    try:
                        os.makedirs('debug', exist_ok=True)
                        dbg = roi.copy()
                        cv2.circle(dbg, (x, y), r, (0, 255, 0), 2)
                        cv2.circle(dbg, (roi_cx, roi_cy), 4, (0, 0, 255), -1)
                        ts = int(time.time())
                        cv2.imwrite(f'debug/circle_{ts}.png', dbg)
                    except Exception:
                        pass
                return True

        if candidates:
            self._log(f"Circle check: {len(candidates)} candidate(s) — none passed thresholds")
        return False


    def _check_gather_ui(self, screenshot):
        """True если добыча идёт — проверяем banner.png (основной) и dobicha.png (резервный).
        Достаточно найти любой из двух шаблонов.
        """
        if screenshot is None:
            return False

        sh, sw = screenshot.shape[:2]

        def _best_match(tpl, thresh, full_screen=False):
            """Ищет tpl на скриншоте, возвращает (score, found)."""
            if tpl is None:
                return 0.0, False
            th, tw = tpl.shape[:2]
            if full_screen:
                roi, ox, oy = screenshot, 0, 0
            else:
                x1 = int(sw * 0.05)
                y1 = 0
                x2 = int(sw * 0.95)
                y2 = sh
                roi = screenshot[y1:y2, x1:x2]
                ox, oy = x1, y1
            rh, rw = roi.shape[:2]
            best = 0.0
            for sc in [1.0, 0.85, 1.15]:
                nw = max(1, int(tw * sc))
                nh = max(1, int(th * sc))
                if nw > rw or nh > rh:
                    continue
                try:
                    t2 = cv2.resize(tpl, (nw, nh), interpolation=cv2.INTER_AREA) if sc != 1.0 else tpl
                    res = cv2.matchTemplate(roi, t2, cv2.TM_CCOEFF_NORMED)
                    _, mx, _, _ = cv2.minMaxLoc(res)
                    if mx > best:
                        best = mx
                except cv2.error:
                    pass
            return best, best >= thresh

        # ── 1. Banner (основной — всегда виден пока идёт добыча) ────────────
        banner_score, banner_hit = _best_match(self._gather_banner_tpl, GATHER_BANNER_THRESH)
        if banner_hit:
            return True

        # ── 2. Dobicha window (резервный) ────────────────────────────────────
        dobicha_score, dobicha_hit = _best_match(self._gather_ui_tpl, GATHER_UI_THRESH)
        if dobicha_hit:
            return True

        # Near-miss лог только если совсем близко к порогу
        best_any = max(banner_score, dobicha_score)
        if best_any >= 0.45:
            self._log(f"gather near-miss: banner={banner_score:.2f} dobicha={dobicha_score:.2f}")

        return False

    def _check_banner_only(self, screenshot):
        """Проверяет ТОЛЬКО banner.png — основной индикатор что добыча действительно идёт.
        Возвращает True если баннер найден на экране.
        """
        if screenshot is None or self._gather_banner_tpl is None:
            return False
        tpl = self._gather_banner_tpl
        th, tw = tpl.shape[:2]
        sh, sw = screenshot.shape[:2]
        best = 0.0
        for sc in [1.0, 0.85, 1.15]:
            nw = max(1, int(tw * sc))
            nh = max(1, int(th * sc))
            if nw > sw or nh > sh:
                continue
            try:
                t2 = cv2.resize(tpl, (nw, nh), interpolation=cv2.INTER_AREA) if sc != 1.0 else tpl
                res = cv2.matchTemplate(screenshot, t2, cv2.TM_CCOEFF_NORMED)
                _, mx, _, _ = cv2.minMaxLoc(res)
                if mx > best:
                    best = mx
            except cv2.error:
                pass
        return best >= GATHER_BANNER_THRESH

    def _search_and_gather_next(self):
        """Search for next free target and click immediately if found.
        Priority:
          -1: BG кандидаты (найдены во время добычи) — сначала пробуем их
           1: vkusnocvet color blobs
           0: povei (только если нет vkusnocvet)
           2: template matching fallback
        """
        if not self.running:
            return
        screenshot = self._grab_screenshot()
        if screenshot is None:
            return
        exclude = self._clicked_recently + self._dead_zones

        # ── Priority -1: BG кандидаты — запомненные во время добычи ────────
        # Проверяем каждого кандидата на текущем скриншоте (цвет ещё есть?)
        # Сортируем: vkusnocvet сначала, потом povei
        bg_candidates = getattr(self, '_bg_candidates', [])
        if bg_candidates:
            bg_sorted = sorted(bg_candidates, key=lambda c: (0 if c[2] == 'vkusnocvet' else 1, -c[3]))
            for bx, by, blabel, bscore in bg_sorted:
                if any(abs(bx - ex) < 55 and abs(by - ey) < 55 for ex, ey, *_ in exclude):
                    continue
                if self._is_occupied(screenshot, bx, by):
                    continue
                color_ok = self._count_resource_pixels_in_circle(screenshot, bx, by, blabel)
                if color_ok < 3:
                    continue
                tidx = next((i for i, tc in enumerate(self._tpl_cache)
                             if tc.get('label') == blabel), -1)
                self._log(f"BG candidate HIT ({bx},{by})[{blabel}] score={bscore}")
                self._bg_candidates = []
                self._do_gather((bx, by), min(0.99, bscore / 500.0), tidx)
                return
            self._log(f"All BG candidates rejected — fresh scan")
            self._bg_candidates = []

        # Priority 1 (early check): color-blob (vkusnocvet) — проверяем ДО повея
        cblobs = self.find_color_blobs(screenshot, exclude)

        # Если вкусноцветы есть но все в cooldown/exclude — не тратим время на повей,
        # сразу скроллим чтобы найти новые свободные ресурсы
        if not cblobs:
            cblobs_all = self.find_color_blobs(screenshot, [])
            if cblobs_all:
                self._log(f"Vkusnocvet blobs visible ({len(cblobs_all)}) but all in exclude — scrolling")
                if not self.dry_run:
                    self._no_match_streak += 1
                    self._try_scroll()
                return

        # Priority 0: повей — только если нет свободного вкусноцвета
        if not cblobs:
            ppos, pconf = self.find_povei_match(screenshot, exclude, self._color_reject_zones)
            if ppos is not None:
                if self._is_occupied(screenshot, ppos[0], ppos[1]):
                    self._log(f"Next povei target occupied at {ppos} — skipping")
                    self._dead_zones.append((ppos[0], ppos[1], time.time()))
                else:
                    tidx = next((i for i,tc in enumerate(self._tpl_cache) if tc.get('label')=='povei'), -1)
                    self._log(f"Next target found (povei): conf={pconf:.3f} pos={ppos}")
                    self._do_gather(ppos, pconf, tidx)
                    return

            # Priority 0b: повей — цветовой детектор (только если нет вкусноцвета)
            pblobs = self.find_povei_color_blobs(screenshot, exclude)
            if pblobs:
                bx, by, bscore = pblobs[0]
                # Skip only if VERY strong vkusnocvet overlap (3x threshold = 120px)
                pv1 = max(0, bx - 36); pv2 = min(screenshot.shape[1], bx + 36)
                ph1 = max(0, by - 36); ph2 = min(screenshot.shape[0], by + 36)
                p_patch_hsv = cv2.cvtColor(screenshot[ph1:ph2, pv1:pv2], cv2.COLOR_BGR2HSV)
                p_h2, p_s2, _ = cv2.split(p_patch_hsv)
                vkusn_px2 = int(np.sum((p_h2 >= COLOR_H_LO) & (p_h2 <= COLOR_H_HI) & (p_s2 >= COLOR_S_MIN)))
                if vkusn_px2 >= COLOR_MIN_PIXELS * 3:
                    self._log(f"Next POVEI-COLOR ({bx},{by}) — strong vkusnocvet overlap (vkusn_px={vkusn_px2}), trying next")
                    pblobs = pblobs[1:]
                if pblobs:
                    bx, by, bscore = pblobs[0]
                    # Проверяем занятость перед кликом
                    if self._is_occupied(screenshot, bx, by):
                        self._log(f"Next POVEI-COLOR ({bx},{by}) occupied — adding to dead_zones")
                        self._dead_zones.append((bx, by, time.time()))
                    else:
                        tidx = next((i for i, tc in enumerate(self._tpl_cache) if tc.get('label') == 'povei'), -1)
                        self._log(f"Next target found (povei-color): ({bx},{by}) score={bscore}")
                        self._do_gather((bx, by), min(0.99, bscore / 30.0), tidx)
                        return
        else:
            self._log(f"Vkusnocvet blobs found ({len(cblobs)}) — skipping povei search")

        # Priority 1: color-blob (vkusnocvet purple/crimson)
        if cblobs:
            bx, by, barea = cblobs[0]
            self._log(f"Next target found (color): ({bx},{by}) area={barea}")
            self._do_gather((bx, by), 0.0, -1)
            return

        # Priority 2: vkusnocvet template matching
        # Запускаем только если color-blobs не дали результата, и только с ограниченным
        # числом шаблонов чтобы не тормозить переход к следующей цели.
        pos, conf, tidx = self.find_vkusn_match(screenshot, exclude, fast=True)
        if conf >= MATCH_THRESHOLD and pos is not None:
            lx, ly = pos
            self._log(f"Next target found (tpl): conf={conf:.3f} local=({lx},{ly})")
            self._do_gather(pos, conf, tidx)
            return

        # Fallback: bright-blob — ОТКЛЮЧЁН (находит скалы)
        # blobs = self.find_bright_blobs(screenshot, exclude)

        self._log("No next target — scrolling to find new candidates")
        if not self.dry_run:
            self._no_match_streak += 1
            self._try_scroll()

    def _scroll_silent(self, notches, repeats=1, focus_click=False):
        """
        Скролл списка охоты стрелками Arrow Down/Up на месте последнего клика.
        Курсор перемещается на позицию последнего ресурса (_last_click_gx/gy),
        затем посылаются нажатия Arrow Down/Up в активное окно браузера.
        notches > 0 → вниз, notches < 0 → вверх.
        """
        if self.dry_run or notches == 0:
            self._log(f"DRY scroll_silent({notches}x{repeats})")
            return
        repeats    = max(1, int(repeats))
        direction  = "down" if notches > 0 else "up"
        total_presses = abs(notches) * repeats
        vk_key = 0x28 if notches > 0 else 0x26  # VK_DOWN=0x28, VK_UP=0x26

        # Позиция для скролла: последний клик по ресурсу
        # (курсор уже там или возвращаем его туда)
        click_x = getattr(self, '_last_click_gx', None)
        click_y = getattr(self, '_last_click_gy', None)

        try:
            if self._is_windows:
                KEYEVENTF_KEYDOWN = 0x0000
                KEYEVENTF_KEYUP   = 0x0002

                # Перемещаем курсор на место последнего клика (фокус на игровом холсте)
                if click_x is not None and click_y is not None:
                    ctypes.windll.user32.SetCursorPos(int(click_x), int(click_y))
                    time.sleep(0.05)

                # Посылаем нажатия стрелки
                for _ in range(total_presses):
                    ctypes.windll.user32.keybd_event(vk_key, 0, KEYEVENTF_KEYDOWN, 0)
                    time.sleep(0.02)
                    ctypes.windll.user32.keybd_event(vk_key, 0, KEYEVENTF_KEYUP,   0)
                    time.sleep(SCROLL_PAUSE)

                self._log(f"Scrolled {direction} {total_presses} arrows at ({click_x},{click_y})")
            else:
                import pyautogui as _pag
                if click_x is not None and click_y is not None:
                    _pag.moveTo(click_x, click_y, duration=0.05)
                key_name = 'down' if notches > 0 else 'up'
                for _ in range(total_presses):
                    _pag.press(key_name)
                    time.sleep(SCROLL_PAUSE)
                self._log(f"Scrolled {direction} {total_presses} arrows at ({click_x},{click_y})")
        except Exception as e:
            self._log(f"scroll_silent error: {e}")

    def _press_esc(self):
        """
        Press ESC key to close the gather window / dismiss any dialog.
        Used after gathering completes so the UI banner closes cleanly.
        """
        if self.dry_run:
            return
        try:
            if self._is_windows:
                VK_ESCAPE = 0x1B
                KEYEVENTF_KEYDOWN = 0x0000
                KEYEVENTF_KEYUP   = 0x0002
                ctypes.windll.user32.keybd_event(VK_ESCAPE, 0, KEYEVENTF_KEYDOWN, 0)
                time.sleep(0.05)
                ctypes.windll.user32.keybd_event(VK_ESCAPE, 0, KEYEVENTF_KEYUP,   0)
                time.sleep(0.1)
            else:
                import pyautogui as _pag
                _pag.press('escape')
                time.sleep(0.1)
            self._log("ESC pressed — gather window dismissed")
        except Exception as e:
            self._log(f"_press_esc error: {e}")

    def _move_cursor_away(self):
        """
        Перемещает курсор в правый нижний угол игрового окна — подальше от
        добываемого ресурса. БЕЗ клика. Вызывается сразу после double-click
        чтобы курсор не перекрывал ресурс во время color-check.
        """
        if self.dry_run:
            return
        try:
            cb = self.cursor_bounds
            # Правый нижний угол — вдали от большинства ресурсов в hunt zone
            ax = cb['x'] + int(cb['width']  * 0.92)
            ay = cb['y'] + int(cb['height'] * 0.92)
            if self._is_windows:
                ctypes.windll.user32.SetCursorPos(int(ax), int(ay))
            else:
                pyautogui.moveTo(ax, ay, duration=0.0)
            pass  # cursor moved away
        except Exception as e:
            self._log(f"move_cursor_away error: {e}")

    def _click_away(self):
        """
        Кликнуть в нейтральную точку игрового поля чтобы снять фокус с баннера.
        Троттлинг: не чаще раз в CLICK_AWAY_COOLDOWN секунд.
        Используется ТОЛЬКО для hint_save_povei и сброса фокуса UI.
        """
        if self.dry_run:
            return
        now = time.time()
        last = getattr(self, '_click_away_ts', 0.0)
        if now - last < CLICK_AWAY_COOLDOWN:
            self._log(f"click_away skipped (cooldown {CLICK_AWAY_COOLDOWN:.0f}s, elapsed {now-last:.1f}s)")
            return
        self._click_away_ts = now
        cb = self.cursor_bounds
        ax = cb['x'] + cb['width'] // 4
        ay = cb['y'] + int(cb['height'] * 0.60)
        try:
            if self._is_windows:
                ctypes.windll.user32.SetCursorPos(int(ax), int(ay))
                time.sleep(0.05)
                ctypes.windll.user32.mouse_event(0x0002, 0, 0, 0, 0)
                time.sleep(0.04)
                ctypes.windll.user32.mouse_event(0x0004, 0, 0, 0, 0)
            else:
                pyautogui.click(ax, ay)
            time.sleep(0.08)
            self._log(f"click_away → ({ax},{ay})")
        except Exception as e:
            self._log(f"click_away error: {e}")

    def _scroll_at_center(self, amount=None, repeats=1):
        """Скролл — делегирует в _scroll_silent (без движения мыши)."""
        notches = amount if amount is not None else SCROLL_AMOUNT
        self._scroll_silent(notches, repeats)

    def _scroll_series(self, amount=None, total_repeats=None):
        """Серия скроллов без движения мыши."""
        notches = amount if amount is not None else SCROLL_AMOUNT
        repeats = total_repeats if total_repeats is not None else SCROLL_REPEATS
        self._scroll_silent(notches, repeats)

    def _try_scroll(self):
        """
        Простой цикличный скролл: 5 нажатий вниз, потом 5 нажатий вверх, повтор.
        _scroll_pos: 0..4 = шаги вниз, 5..9 = шаги вверх.
        Вызывается каждый раз когда нет подходящего ресурса.
        """
        if self._boi_active:
            return

        # Убираем маркеры кандидатов ДО скролла — после скролла позиции устареют
        self._emit("HIDE_CANDIDATES")

        pos = getattr(self, '_scroll_pos', 0)
        half = SCROLL_CYCLE_STEPS  # 5

        if pos < half:
            # Шаги 0..4 — вниз
            self._log(f"Scroll DOWN step {pos+1}/{half}")
            self._scroll_silent(SCROLL_AMOUNT, 1)
        else:
            # Шаги 5..9 — вверх
            self._log(f"Scroll UP step {pos-half+1}/{half}")
            self._scroll_silent(-SCROLL_AMOUNT, 1)
            # При движении вверх сбрасываем зоны — ресурсы могли обновиться
            self._dead_zones       = []
            self._clicked_recently = []

        self._color_reject_zones = []

        # Сдвигаем позицию цикла
        self._scroll_pos = (pos + 1) % (half * 2)

        # После скролла — пересчитываем кандидатов
        post_shot = self._grab_screenshot()
        if post_shot is not None:
            exclude = self._clicked_recently + self._dead_zones
            self._emit_candidates(post_shot, exclude_pos=exclude)

    # ── template matching ───────────────────────────────────────────────────────

    @staticmethod
    def _make_fg_mask(img):
        """
        Extract foreground mask: remove background by corner pixel color.
        Returns 0/255 mask of same size.
        """
        h, w = img.shape[:2]
        # Sample color from 4 corners as background
        corners = [img[0,0], img[0,w-1], img[h-1,0], img[h-1,w-1]]
        mask = np.ones((h, w), dtype=np.uint8) * 255
        for c in corners:
            lo = np.clip(c.astype(int) - 30, 0, 255).astype(np.uint8)
            hi = np.clip(c.astype(int) + 30, 0, 255).astype(np.uint8)
            bg = cv2.inRange(img, lo, hi)
            mask = cv2.bitwise_and(mask, cv2.bitwise_not(bg))
        # Morphology: close small holes
        kernel = cv2.getStructuringElement(cv2.MORPH_ELLIPSE, (5,5))
        mask = cv2.morphologyEx(mask, cv2.MORPH_CLOSE, kernel)
        return mask

    @staticmethod
    def _preprocess(img):
        """
        Returns tuple (gray_eq, hue, edges) for matching.
        gray_eq  — equalized brightness (CLAHE)
        hue      — H channel from HSV (color feature)
        edges    — Canny contours
        """
        gray = cv2.cvtColor(img, cv2.COLOR_BGR2GRAY)
        clahe = cv2.createCLAHE(clipLimit=2.0, tileGridSize=(4,4))
        gray_eq = clahe.apply(gray)
        hsv = cv2.cvtColor(img, cv2.COLOR_BGR2HSV)
        hue = hsv[:,:,0]
        edges = cv2.Canny(gray_eq, 40, 120)
        return gray_eq, hue, edges

    def _build_enhanced_templates(self):
        """Preprocess templates once at load time."""
        self._tpl_cache = []
        for i, tpl in enumerate(self.sample_templates):
            mask    = self._make_fg_mask(tpl)
            gray_eq, hue, edges = self._preprocess(tpl)
            hue_m   = cv2.bitwise_and(hue,   hue,   mask=mask)
            edges_m = cv2.bitwise_and(edges, edges, mask=mask)
            label   = self.recorded_samples[i].get('label', '?') if i < len(self.recorded_samples) else '?'
            image   = self.recorded_samples[i].get('image', '?') if i < len(self.recorded_samples) else '?'
            self._tpl_cache.append({
                'bgr':    tpl,
                'gray':   gray_eq,
                'hue':    hue_m,
                'edges':  edges_m,
                'mask':   mask,
                'label':  label,
                'image':  image,
            })
        # Count by label
        from collections import Counter
        counts = Counter(tc['label'] for tc in self._tpl_cache)
        self._log(f"Enhanced template cache: {len(self._tpl_cache)} templates {dict(counts)}")

    def find_bright_blobs(self, screenshot, exclude_positions=None):
        """
        Find resource objects (повей, вкусноцвет) by detecting bright glowing pixels
        that sit ON green grass. STRICT filtering to reduce false positives.

        Algorithm:
          1. Build green-grass mask (HSV hue 25-88, moderate sat/val)
          2. Dilate grass mask so flowers just above ground are included
          3. Build bright-glow mask (V > BLOB_V_THRESH, S < BLOB_S_THRESH)
          4. Intersect: only bright pixels that are on/near grass
          5. Find contours within size range
          6. CHECK HUNT WINDOW ROI (strict)
          7. FILTER by shape compactness (circularity)
          8. CHECK occupation status
          9. VERIFY with selection circle

        Calibrated on Location_1.png (57 blobs) vs Location_2.png (1 blob).
        """
        if screenshot is None:
            return []

        sh, sw = screenshot.shape[:2]
        hsv = cv2.cvtColor(screenshot, cv2.COLOR_BGR2HSV)
        h_ch, s_ch, v_ch = cv2.split(hsv)

        # ── Step 1: Green grass mask ───────────────────────────────────────────
        grass = (
            (h_ch >= BLOB_GRASS_H_LO) & (h_ch <= BLOB_GRASS_H_HI) &
            (s_ch > BLOB_GRASS_S_MIN) & (v_ch > BLOB_GRASS_V_MIN) &
            (v_ch < BLOB_GRASS_V_MAX)
        ).astype(np.uint8) * 255

        # ── Step 2: Dilate grass so flowers on grass are covered ───────────────
        k_grass = cv2.getStructuringElement(cv2.MORPH_ELLIPSE, (BLOB_GRASS_DILATE, BLOB_GRASS_DILATE))
        grass_dilated = cv2.dilate(grass, k_grass)

        # ── Step 3: Bright-glow mask ───────────────────────────────────────────
        bright = (
            (v_ch > BLOB_V_THRESH) & (s_ch < BLOB_S_THRESH)
        ).astype(np.uint8) * 255
        k_close = cv2.getStructuringElement(cv2.MORPH_ELLIPSE, (BLOB_MORPH_K, BLOB_MORPH_K))
        bright_closed = cv2.morphologyEx(bright, cv2.MORPH_CLOSE, k_close)

        # ── Step 4: Intersect — bright blobs on green ground ──────────────────
        on_grass = cv2.bitwise_and(bright_closed, grass_dilated)

        # ── Step 5: Find contours inside hunt window ROI (STRICT) ──────────────
        roi_mask = np.zeros((sh, sw), dtype=np.uint8)
        hx1 = self.hunt_left
        hy1 = self.hunt_top
        hx2 = sw - self.hunt_right
        hy2 = sh - self.hunt_bottom
        if hx2 > hx1 and hy2 > hy1:
            roi_mask[hy1:hy2, hx1:hx2] = on_grass[hy1:hy2, hx1:hx2]

        contours, _ = cv2.findContours(roi_mask, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)

        results = []
        for c in contours:
            area = cv2.contourArea(c)
            if area < BLOB_MIN_AREA or area > BLOB_MAX_AREA:
                continue

            bx, by, bw, bh = cv2.boundingRect(c)
            cx = bx + bw // 2
            cy = by + bh // 2

            # ── Filter 1: Skip cooldown / dead zones ─────────────────────────────
            if exclude_positions and any(
                abs(cx - ex) < CLICK_RADIUS and abs(cy - ey) < CLICK_RADIUS
                for ex, ey, *_ in exclude_positions
            ):
                continue

            # ── Filter 2: Shape compactness (circularity) ───────────────────────
            # Compact blobs: circularity = 4*pi*area / perimeter^2 should be > 0.5
            perimeter = cv2.arcLength(c, True)
            if perimeter > 0:
                circularity = 4 * np.pi * area / (perimeter ** 2)
            else:
                circularity = 0
            if circularity < 0.4:  # Too elongated/irregular — false positive
                continue

            # ── Filter 3: Check occupation status ────────────────────────────────
            if self._is_occupied(screenshot, cx, cy):
                continue

            results.append((cx, cy, int(area)))

        results.sort(key=lambda r: -r[2])

        if results:
            self._log(f"Grass blobs: {len(results)} found, top=({results[0][0]},{results[0][1]}) area={results[0][2]}")
            # Save debug image periodically (at most once per 30s)
            now = time.time()
            if not hasattr(self, '_last_blob_debug_ts') or now - self._last_blob_debug_ts > 30.0:
                self._last_blob_debug_ts = now
                try:
                    os.makedirs('debug', exist_ok=True)
                    dbg = screenshot.copy()
                    # tint grass area
                    dbg[grass_dilated > 0] = (
                        dbg[grass_dilated > 0].astype(np.float32) * 0.75 +
                        np.array([0, 60, 0], dtype=np.float32) * 0.25
                    ).astype(np.uint8)
                    # Draw hunt window boundary in green
                    cv2.rectangle(dbg, (hx1, hy1), (hx2, hy2), (0, 255, 0), 2)
                    for i, (cx, cy, area) in enumerate(results[:20]):
                        cv2.circle(dbg, (cx, cy), 16, (0, 255, 255), 2)
                        cv2.putText(dbg, str(i + 1), (cx - 5, cy + 5),
                                    cv2.FONT_HERSHEY_SIMPLEX, 0.5, (0, 0, 255), 1)
                    cv2.imwrite('debug/blobs_live.png', dbg)
                except Exception:
                    pass
        else:
            self._log("Grass blobs: 0 found")
        return results

    def find_color_blobs(self, screenshot, exclude_positions=None):
        """
        Find vkusnocvet flower by its characteristic purple/crimson colors:
          #A551BC (purple H=144 S=145 V=188)  → mask1: H=130..155
          #830E43 (crimson H=166 S=228 V=131) → mask2: H=155..175
        NOTE: povei (повей-трава) is teal/cyan (H=18-30) which overlaps with water —
              povei is detected via template matching (povei_pattern.png), NOT color blobs.
        Searches ONLY inside the hunt window.
        Returns list of (cx, cy, area) sorted by area descending.
        """
        if screenshot is None:
            return []

        sh, sw = screenshot.shape[:2]
        hsv = cv2.cvtColor(screenshot, cv2.COLOR_BGR2HSV)

        # Объединённая маска вкусноцвета по COLOR_H_LO..COLOR_H_HI (обновлена с учётом
        # затемнения при добыче: S_MIN=50, V_MIN=34 вместо 80/70).
        # Mask 1: purple (#A551BC H=144) — H=COLOR_H_LO..155
        lo1 = np.array([COLOR_H_LO, COLOR_S_MIN, COLOR_V_MIN], dtype=np.uint8)
        hi1 = np.array([155,        255,          COLOR_V_MAX], dtype=np.uint8)
        mask1 = cv2.inRange(hsv, lo1, hi1)

        # Mask 2: crimson (#830E43 H=166) — H=155..COLOR_H_HI
        lo2 = np.array([155,        COLOR_S_MIN, COLOR_V_MIN], dtype=np.uint8)
        hi2 = np.array([COLOR_H_HI, 255,         COLOR_V_MAX], dtype=np.uint8)
        mask2 = cv2.inRange(hsv, lo2, hi2)

        mask = cv2.bitwise_or(mask1, mask2)

        # Morphology: close small gaps
        k = cv2.getStructuringElement(cv2.MORPH_ELLIPSE, (COLOR_MORPH_K, COLOR_MORPH_K))
        mask = cv2.morphologyEx(mask, cv2.MORPH_CLOSE, k)

        # ── Restrict STRICTLY to hunt window ──────────────────────────────────
        hx1 = self.hunt_left
        hy1 = self.hunt_top
        hx2 = sw - self.hunt_right
        hy2 = sh - self.hunt_bottom
        roi_mask = np.zeros((sh, sw), dtype=np.uint8)
        if hx2 > hx1 and hy2 > hy1:
            roi_mask[hy1:hy2, hx1:hx2] = mask[hy1:hy2, hx1:hx2]

        contours, _ = cv2.findContours(roi_mask, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)

        results = []
        for c in contours:
            area = cv2.contourArea(c)
            if area < COLOR_MIN_AREA or area > COLOR_MAX_AREA:
                continue
            bx, by, bw, bh = cv2.boundingRect(c)
            cx = bx + bw // 2
            cy = by + bh // 2
            if exclude_positions and any(
                abs(cx - ex) < CLICK_RADIUS and abs(cy - ey) < CLICK_RADIUS
                for ex, ey, *_ in exclude_positions
            ):
                continue

            # ── Pixel count check: vkusnocvet has many color pixels, povei has few ──
            # Extract patch around centroid to count actual colored pixels
            pad = 32
            px1 = max(0, cx - pad); py1 = max(0, cy - pad)
            px2 = min(sw, cx + pad); py2 = min(sh, cy + pad)
            patch_mask = roi_mask[py1:py2, px1:px2]
            actual_px = int(np.sum(patch_mask > 0))
            if actual_px < COLOR_MIN_PIXELS:
                # Too few colored pixels — likely povei mis-detected as vkusnocvet
                continue

            occupied = self._is_occupied(screenshot, cx, cy)
            if occupied:
                continue
            results.append((cx, cy, int(area)))

        # Sort: by area descending
        results.sort(key=lambda r: -r[2])

        if results:
            pass
            now = time.time()
            if not hasattr(self, '_last_color_debug_ts') or now - self._last_color_debug_ts > 30.0:
                self._last_color_debug_ts = now
                try:
                    os.makedirs('debug', exist_ok=True)
                    dbg = screenshot.copy()
                    dbg[roi_mask > 0] = (0, 220, 255)  # highlight in orange-yellow
                    # Draw hunt window boundary in green
                    cv2.rectangle(dbg, (hx1, hy1), (hx2, hy2), (0, 255, 0), 2)
                    for i, (cx, cy, area) in enumerate(results[:20]):
                        cv2.circle(dbg, (cx, cy), 18, (0, 0, 255), 2)
                        cv2.putText(dbg, str(i + 1), (cx - 5, cy + 5),
                                    cv2.FONT_HERSHEY_SIMPLEX, 0.5, (255, 255, 255), 1)
                    cv2.imwrite('debug/color_blobs_live.png', dbg)
                except Exception:
                    pass
        else:
            pass
        return results

    def find_povei_blobs(self, screenshot, exclude_positions=None):
        """DEPRECATED — повей теперь ищется через template matching в find_best_match."""
        return []

    # Радиус круговой маски для color-delta проверки (соответствует красному кольцу на экране)
    GATHER_CIRCLE_RADIUS = 32

    def _count_resource_pixels_in_circle(self, screenshot, cx, cy, label):
        """
        Считает пиксели цвета ресурса ТОЛЬКО внутри круга радиуса GATHER_CIRCLE_RADIUS
        вокруг точки (cx, cy) — строго как красное кольцо на экране.
        Возвращает количество пикселей или -1 при ошибке.
        """
        if screenshot is None:
            return -1
        R = self.GATHER_CIRCLE_RADIUS
        h, w = screenshot.shape[:2]
        x1 = max(0, cx - R); x2 = min(w, cx + R)
        y1 = max(0, cy - R); y2 = min(h, cy + R)
        if x2 <= x1 or y2 <= y1:
            return -1
        patch = screenshot[y1:y2, x1:x2]
        if patch.size == 0:
            return -1

        # Круговая маска — только пиксели внутри круга R
        ph, pw = patch.shape[:2]
        circle_mask = np.zeros((ph, pw), dtype=np.uint8)
        # Центр патча (смещение из-за crop к краям экрана)
        local_cx = cx - x1
        local_cy = cy - y1
        cv2.circle(circle_mask, (local_cx, local_cy), R, 255, -1)

        hsv = cv2.cvtColor(patch, cv2.COLOR_BGR2HSV)

        if label == 'vkusnocvet':
            h_ch, s_ch, _ = cv2.split(hsv)
            color_mask = ((h_ch >= COLOR_H_LO) & (h_ch <= COLOR_H_HI) & (s_ch >= COLOR_S_MIN)).astype(np.uint8)
            return int(np.sum((color_mask > 0) & (circle_mask > 0)))
        elif label == 'povei':
            lo_dark = np.array([POVEI_COLOR_DARK_H_LO, POVEI_COLOR_DARK_S_MIN, POVEI_COLOR_DARK_V_MIN], np.uint8)
            hi_dark = np.array([POVEI_COLOR_DARK_H_HI, 255,                    POVEI_COLOR_DARK_V_MAX], np.uint8)
            lo_pink = np.array([POVEI_COLOR_PINK_H_LO, POVEI_COLOR_PINK_S_MIN, POVEI_COLOR_PINK_V_MIN], np.uint8)
            hi_pink = np.array([POVEI_COLOR_PINK_H_HI, 255,                    255                   ], np.uint8)
            mask_dark = cv2.inRange(hsv, lo_dark, hi_dark)
            mask_pink = cv2.inRange(hsv, lo_pink, hi_pink)
            return int(np.sum(((mask_dark > 0) | (mask_pink > 0)) & (circle_mask > 0)))
        return -1

    def _resource_color_changed_to_green(self, screenshot, cx, cy, label):
        """
        Проверяет исчезновение ресурса по количеству цветовых пикселей
        строго внутри круга GATHER_CIRCLE_RADIUS вокруг точки клика
        (соответствует красному кольцу на экране).

        Ресурс считается исчезнувшим если:
          cur_res_px < max(2, ref_res_px * 0.15)
        и это подтверждается COLOR_GONE_CONSEC_REQUIRED фреймов подряд.
        """
        if screenshot is None:
            return False

        ref_res_px = getattr(self, '_gather_ref_res_px', 0)
        if ref_res_px <= 0:
            return False

        cur_res_px = self._count_resource_pixels_in_circle(screenshot, cx, cy, label)
        if cur_res_px < 0:
            return False

        # Порог 15% от ref — при реальном исчезновении cur падает до 0-5px
        threshold = max(2, int(ref_res_px * 0.15))
        gone_now  = cur_res_px < threshold

        self._log(f"[color-delta] {label} ({cx},{cy}): ref={ref_res_px} cur={cur_res_px} thr={threshold} → {'GONE' if gone_now else 'present'}")

        if gone_now:
            self._color_gone_consec = getattr(self, '_color_gone_consec', 0) + 1
            if self._color_gone_consec >= COLOR_GONE_CONSEC_REQUIRED:
                self._color_gone_consec = 0
                return True
        else:
            self._color_gone_consec = 0
        return False

    def _set_gather_ref(self, screenshot, cx, cy, label):
        """
        Сохраняет эталонное кол-во ресурсных пикселей внутри круга GATHER_CIRCLE_RADIUS
        вокруг точки клика. Вызывается один раз при confirmed=True + GATHER_REF_DELAY_SECS.
        """
        if screenshot is None:
            self._gather_ref_patch  = None
            self._gather_ref_res_px = 0
            return

        res_px = self._count_resource_pixels_in_circle(screenshot, cx, cy, label)
        if res_px < 0:
            self._gather_ref_patch  = None
            self._gather_ref_res_px = 0
            return

        # Сохраняем patch для debug
        R = self.GATHER_CIRCLE_RADIUS
        h, w = screenshot.shape[:2]
        x1 = max(0, cx - R); x2 = min(w, cx + R)
        y1 = max(0, cy - R); y2 = min(h, cy + R)
        self._gather_ref_patch  = screenshot[y1:y2, x1:x2].copy()
        self._gather_ref_res_px = res_px
        self._log(f"[gather-ref] {label} ({cx},{cy}): ref_res_px={res_px} circle_r={R}")

    def _resource_color_present(self, screenshot, cx, cy, label):
        """
        Быстрая проверка: есть ли ещё цвет ресурса вблизи позиции (cx, cy).
        Используется во время добычи чтобы мгновенно обнаружить исчезновение цветка.
        Возвращает True если ресурс ещё виден, False если исчез.
        """
        if screenshot is None:
            return True  # не можем проверить — считаем что есть
        h, w = screenshot.shape[:2]
        pad = 50  # радиус поиска вокруг позиции клика
        x1 = max(0, cx - pad); x2 = min(w, cx + pad)
        y1 = max(0, cy - pad); y2 = min(h, cy + pad)
        if x2 <= x1 or y2 <= y1:
            return True
        patch = screenshot[y1:y2, x1:x2]
        if patch.size == 0:
            return True
        hsv = cv2.cvtColor(patch, cv2.COLOR_BGR2HSV)

        if label == 'povei':
            # Повей: тёмно-бордово (#430006) или розовый (#E33789)
            lo_dark = np.array([POVEI_COLOR_DARK_H_LO, POVEI_COLOR_DARK_S_MIN, POVEI_COLOR_DARK_V_MIN], np.uint8)
            hi_dark = np.array([POVEI_COLOR_DARK_H_HI, 255, POVEI_COLOR_DARK_V_MAX], np.uint8)
            lo_pink = np.array([POVEI_COLOR_PINK_H_LO, POVEI_COLOR_PINK_S_MIN, POVEI_COLOR_PINK_V_MIN], np.uint8)
            hi_pink = np.array([POVEI_COLOR_PINK_H_HI, 255, 255], np.uint8)
            dark_px = int(np.sum(cv2.inRange(hsv, lo_dark, hi_dark) > 0))
            pink_px = int(np.sum(cv2.inRange(hsv, lo_pink, hi_pink) > 0))
            present = (dark_px >= POVEI_COLOR_DARK_MIN_PX) or (pink_px >= POVEI_COLOR_PINK_ONLY_MIN)
            self._log(f"Color check povei ({cx},{cy}): dark={dark_px} pink={pink_px} → {'present' if present else 'GONE'}")
            return present
        else:
            # Вкусноцвет: пурпурный/малиновый H=COLOR_H_LO..COLOR_H_HI
            lo_v = np.array([COLOR_H_LO, COLOR_S_MIN, COLOR_V_MIN], np.uint8)
            hi_v = np.array([COLOR_H_HI, 255, COLOR_V_MAX], np.uint8)
            vkusn_px = int(np.sum(cv2.inRange(hsv, lo_v, hi_v) > 0))
            present = vkusn_px >= COLOR_MIN_PIXELS // 2
            self._log(f"Color check vkusnocvet ({cx},{cy}): vkusn_px={vkusn_px} → {'present' if present else 'GONE'}")
            return present

    def _is_occupied(self, screenshot, cx, cy):
        """
        Проверяет, занят ли ресурс другим игроком.
        Под занятым ресурсом отображается ЖЁЛТАЯ цифра (например '1').
        Ищем жёлтые пиксели в полосе НИЖЕ центра ресурса (cy+10..cy+50, ширина ±25px).
        Возвращает True если жёлтая цифра найдена (ресурс занят).
        """
        if screenshot is None:
            return False
        h, w = screenshot.shape[:2]
        # Полоса строго ПОД центром ресурса — цифра добывающего игрока
        # отображается ~5-35px ниже центра, шириной ±15px.
        # Порог: >= 40 жёлтых пикселей (цифра — компактный объект с чёткими пикселями,
        # не размытое пятно от цветка).
        y1 = min(h - 1, cy + 5)
        y2 = min(h, cy + 38)
        x1 = max(0, cx - 15)
        x2 = min(w, cx + 15)
        if y2 <= y1 or x2 <= x1:
            return False
        patch = screenshot[y1:y2, x1:x2]
        if patch.size == 0:
            return False
        # Жёлтая цифра: HSV Hue=15..35, S>=150, V>=180 — насыщенный яркий жёлтый
        hsv = cv2.cvtColor(patch, cv2.COLOR_BGR2HSV)
        lo_yellow = np.array([15, 150, 180], dtype=np.uint8)
        hi_yellow = np.array([35, 255, 255], dtype=np.uint8)
        yellow_mask = cv2.inRange(hsv, lo_yellow, hi_yellow)
        yellow_px = int(np.sum(yellow_mask > 0))
        if yellow_px >= 40:
            return True
        return False

    def scan_povei_once(self):
        """Diagnostic: runs template matching for povei inside hunt window, saves debug image.
        При нахождении — подсвечивает зелёным квадратом в игровом окне."""
        self._log("=== SCAN POVEI (template matching in hunt ROI) ===")
        shot = self._grab_screenshot()
        if shot is None:
            self._log("ERROR: could not grab screenshot")
            print('SCAN_POVEI_RESULT:{"count":0,"error":"no screenshot","h_lo":0,"h_hi":0,"s_min":0,"v_min":0}', flush=True)
            return

        sh, sw = shot.shape[:2]
        povei_tpls = [tc for tc in self._tpl_cache if tc.get('label') == 'povei']
        self._log(f"Povei templates in cache: {len(povei_tpls)}")

        hx1 = max(0, self.hunt_left)
        hy1 = max(0, self.hunt_top)
        hx2 = min(sw, sw - self.hunt_right)
        hy2 = min(sh, sh - self.hunt_bottom)

        pos, conf, tidx = self.find_best_match(shot)
        label = self._tpl_cache[tidx]['label'] if (self._tpl_cache and 0 <= tidx < len(self._tpl_cache)) else '?'
        found = 1 if (conf >= POVEI_MATCH_THRESHOLD and label == 'povei') else 0

        # Подсвечиваем найденный повей зелёным квадратом в игровом окне
        if found and pos:
            self._emit(f"SHOW_SQUARE:{pos[0]},{pos[1]},povei")
            self._log(f"SCAN: povei found at {pos} conf={conf:.3f} — showing green square")

        os.makedirs('debug', exist_ok=True)
        ts = int(time.time())
        dbg = shot.copy()
        cv2.rectangle(dbg, (hx1, hy1), (hx2, hy2), (0, 220, 255), 2)
        cv2.putText(dbg, "HUNT WINDOW", (hx1 + 4, hy1 + 20),
                    cv2.FONT_HERSHEY_SIMPLEX, 0.5, (0, 220, 255), 1)
        if found and pos:
            cv2.circle(dbg, pos, 28, (0, 255, 0), 3)
            cv2.putText(dbg, f'POVEI {conf:.2f}', (pos[0]-30, pos[1]-32),
                        cv2.FONT_HERSHEY_SIMPLEX, 0.65, (0, 255, 0), 2)
        elif pos:
            cv2.circle(dbg, pos, 24, (0, 80, 255), 2)
            cv2.putText(dbg, f'{label} {conf:.2f}', (pos[0]-30, pos[1]-28),
                        cv2.FONT_HERSHEY_SIMPLEX, 0.55, (0, 80, 255), 1)
        info = f"povei_templates={len(povei_tpls)} best_conf={conf:.3f} label={label} found={found}"
        cv2.putText(dbg, info, (10, 30), cv2.FONT_HERSHEY_SIMPLEX, 0.55, (255, 255, 0), 1)
        cv2.imwrite(f'debug/povei_scan_{ts}_result.png', dbg)
        self._log(f"Debug saved: debug/povei_scan_{ts}_result.png  conf={conf:.3f} label={label}")
        print(f'SCAN_POVEI_RESULT:{{"count":{found},"conf":{round(conf,3)},"templates":{len(povei_tpls)},"h_lo":0,"h_hi":0,"s_min":0,"v_min":0,"ts":{ts}}}', flush=True)

    @staticmethod
    def analyze_povei_colors_from_samples():
        """Counts povei template samples. Template matching mode — no HSV analysis."""
        povei_dir = os.path.join('training_data', 'povei')
        files = [f for f in os.listdir(povei_dir) if f.endswith('.png')] if os.path.isdir(povei_dir) else []
        n = len(files)
        print(f'ANALYZE_POVEI_RESULT:{{"count":{n},"h_mean":0,"h_std":0,"s_mean":0,"s_std":0,"v_mean":0,"v_std":0,"h_lo_rec":0,"h_hi_rec":0,"s_lo_rec":0,"v_lo_rec":0,"updated":false}}', flush=True)
        print(f"Povei template samples: {n}  (template matching — no HSV thresholds needed)", flush=True)

    def find_povei_color_blobs(self, screenshot, exclude_positions=None):
        """
        Быстрый цветовой детектор повея по паттерну двух маркеров:
          #430006 (тёмно-бордовый)  → HSV H=160..179, S>=130, V=5..135  (основной)
          #E33789 (розово-малиновый) → HSV H=150..179, S>=130, V>=20     (доп/fallback)
        Обновлено с учётом затемнения при добыче: V_MIN снижен 150→20 для розового,
        S_MIN снижен 180→130 для тёмного (анализ 92 сэмплов по группам яркости).
        Срабатывает если:
          - dark_px >= POVEI_COLOR_DARK_MIN_PX (основной маркер)
          - ИЛИ pink_px >= POVEI_COLOR_PINK_ONLY_MIN (fallback — только розовый)
        Поиск ТОЛЬКО внутри hunt window.
        Возвращает список (cx, cy, score) отсортированный по убыванию score.
        """
        if screenshot is None:
            return []
        sh, sw = screenshot.shape[:2]
        hx1 = max(0, self.hunt_left)
        hy1 = max(0, self.hunt_top)
        hx2 = min(sw, sw - self.hunt_right)
        hy2 = min(sh, sh - self.hunt_bottom)
        if hx2 <= hx1 or hy2 <= hy1:
            return []

        roi = screenshot[hy1:hy2, hx1:hx2]
        hsv = cv2.cvtColor(roi, cv2.COLOR_BGR2HSV)

        # Основная маска: тёмно-бордово (#430006) — H=160..179, S>=180, V=5..120
        lo_dark = np.array([POVEI_COLOR_DARK_H_LO, POVEI_COLOR_DARK_S_MIN, POVEI_COLOR_DARK_V_MIN], np.uint8)
        hi_dark = np.array([POVEI_COLOR_DARK_H_HI, 255, POVEI_COLOR_DARK_V_MAX], np.uint8)
        mask_dark = cv2.inRange(hsv, lo_dark, hi_dark)

        # Дополнительная маска: розово-малиновый (#E33789) — H=150..175, S>=130, V>=150
        lo_pink = np.array([POVEI_COLOR_PINK_H_LO, POVEI_COLOR_PINK_S_MIN, POVEI_COLOR_PINK_V_MIN], np.uint8)
        hi_pink = np.array([POVEI_COLOR_PINK_H_HI, 255, 255], np.uint8)
        mask_pink = cv2.inRange(hsv, lo_pink, hi_pink)

        # Морфология — объединяем рядом стоящие пиксели в компоненты
        k = cv2.getStructuringElement(cv2.MORPH_ELLIPSE,
                                       (POVEI_COLOR_MORPH_K, POVEI_COLOR_MORPH_K))
        mask_dark_closed = cv2.morphologyEx(mask_dark, cv2.MORPH_CLOSE, k)
        mask_pink_closed  = cv2.morphologyEx(mask_pink,  cv2.MORPH_CLOSE, k)

        # Объединённая маска кандидатов (dark + pink)
        mask_all = cv2.bitwise_or(mask_dark_closed, mask_pink_closed)

        num_labels, labels_map, stats, centroids = cv2.connectedComponentsWithStats(
            mask_all, connectivity=8)

        results = []
        for lbl in range(1, num_labels):
            area = int(stats[lbl, cv2.CC_STAT_AREA])
            if area < POVEI_COLOR_MIN_AREA or area > POVEI_COLOR_MAX_AREA:
                continue
            cx_roi = int(centroids[lbl][0])
            cy_roi = int(centroids[lbl][1])
            cx = cx_roi + hx1
            cy = cy_roi + hy1

            # Суммарное кол-во dark и pink пикселей в расширенном патче вокруг компоненты
            pad = 28
            rx1 = max(0, cx_roi - pad)
            ry1 = max(0, cy_roi - pad)
            rx2 = min(mask_dark.shape[1], cx_roi + pad)
            ry2 = min(mask_dark.shape[0], cy_roi + pad)
            dark_px = int(np.sum(mask_dark[ry1:ry2, rx1:rx2] > 0))
            pink_px = int(np.sum(mask_pink[ry1:ry2, rx1:rx2] > 0))

            # Основной маркер: достаточно тёмно-бордового
            # Fallback: если dark=0 но розового много — тоже считаем
            if dark_px >= POVEI_COLOR_DARK_MIN_PX:
                score = dark_px * 2 + pink_px
            elif pink_px >= POVEI_COLOR_PINK_ONLY_MIN:
                score = pink_px  # только розовый — меньшая уверенность
            else:
                continue  # ни того ни другого — пропускаем

            if exclude_positions and any(
                abs(cx - ex) < CLICK_RADIUS and abs(cy - ey) < CLICK_RADIUS
                for ex, ey, *_ in exclude_positions
            ):
                continue

            if self._is_occupied(screenshot, cx, cy):
                continue

            results.append((cx, cy, int(score)))

        # Дедупликация по близости (55px)
        deduped = []
        for cx, cy, sc in sorted(results, key=lambda r: -r[2]):
            if any(abs(cx - dx) < 55 and abs(cy - dy) < 55 for dx, dy, _ in deduped):
                continue
            deduped.append((cx, cy, sc))

        return deduped

    def find_povei_match(self, screenshot, exclude_positions=None, color_reject_zones=None):
        """
        Поиск повея: template matching по всем шаблонам label='povei'.
        Собирает top-N кандидатов (NMS, радиус 60px), затем проверяет каждого по цвету.
        Позиции из color_reject_zones пропускаются сразу (были отклонены недавно).
        Возвращает (pos, conf) или (None, 0.0).
        """
        if not self._tpl_cache:
            return None, 0.0

        sh, sw = screenshot.shape[:2]
        hx1 = max(0, self.hunt_left)
        hy1 = max(0, self.hunt_top)
        hx2 = min(sw, sw - self.hunt_right)
        hy2 = min(sh, sh - self.hunt_bottom)
        if hx2 <= hx1 or hy2 <= hy1:
            return None, 0.0

        hunt = screenshot[hy1:hy2, hx1:hx2]
        if hunt.size == 0:
            return None, 0.0

        hunt_gray = cv2.cvtColor(hunt, cv2.COLOR_BGR2GRAY)
        clahe = cv2.createCLAHE(clipLimit=2.0, tileGridSize=(4, 4))
        hunt_gray_eq = clahe.apply(hunt_gray)

        povei_tpls = [tc for tc in self._tpl_cache if tc.get('label') == 'povei']
        if not povei_tpls:
            self._log("Povei: no templates in cache with label='povei'")
            return None, 0.0

        hh, hw = hunt.shape[:2]

        # ── Шаг 1: для каждого шаблона×масштаба → один глобальный максимум ──
        raw_hits = []  # list of (val, cx_global, cy_global)
        for tc in povei_tpls:
            tpl_gray = tc['gray']
            th, tw = tpl_gray.shape[:2]
            if th < 4 or tw < 4:
                continue
            for sc in POVEI_MATCH_SCALES:
                nw = max(4, int(tw * sc))
                nh = max(4, int(th * sc))
                if nw >= hw or nh >= hh:
                    continue
                t_rs = cv2.resize(tpl_gray, (nw, nh), interpolation=cv2.INTER_AREA)
                try:
                    res = cv2.matchTemplate(hunt_gray_eq, t_rs, cv2.TM_CCOEFF_NORMED)
                except cv2.error:
                    continue
                _, mx_val, _, mx_loc = cv2.minMaxLoc(res)
                if mx_val < POVEI_MATCH_THRESHOLD:
                    continue
                cx_g = mx_loc[0] + nw // 2 + hx1
                cy_g = mx_loc[1] + nh // 2 + hy1
                raw_hits.append((float(mx_val), cx_g, cy_g))

        if not raw_hits:
            self._log(f"Povei: no match above threshold={POVEI_MATCH_THRESHOLD} (tpls={len(povei_tpls)})")
            return None, 0.0

        # ── Шаг 2: NMS — top-3 уникальных позиций (радиус 60px) ──────────────
        NMS_RADIUS = 60
        MAX_CANDIDATES = 3
        raw_hits.sort(key=lambda h: -h[0])
        candidates = []
        for val, cx, cy in raw_hits:
            if any(abs(cx - ac) < NMS_RADIUS and abs(cy - ay) < NMS_RADIUS
                   for _, ac, ay in candidates):
                continue
            candidates.append((val, cx, cy))
            if len(candidates) >= MAX_CANDIDATES:
                break

        # ── Шаг 3: проверяем каждого кандидата ────────────────────────────────
        # Samples analysis: all 124 povei samples have dark>=3 and pink>=3 in 64x64
        # So any real povei flower at the match position WILL have dark+pink pixels.
        # If dark=0 AND pink=0 → grass-only match (no flower), reject.
        # Threshold kept at 1 each to be permissive — false positives caught by dobicha check.
        VERIFY_DARK_MIN = 1
        VERIFY_PINK_MIN = 1
        verify_half = POVEI_CROP_HALF + 20  # 52px radius = 104x104 patch (wider than 64x64 template)

        lo_dark = np.array([POVEI_COLOR_DARK_H_LO, POVEI_COLOR_DARK_S_MIN, POVEI_COLOR_DARK_V_MIN], np.uint8)
        hi_dark = np.array([POVEI_COLOR_DARK_H_HI, 255, POVEI_COLOR_DARK_V_MAX], np.uint8)
        lo_pink = np.array([POVEI_COLOR_PINK_H_LO, POVEI_COLOR_PINK_S_MIN, POVEI_COLOR_PINK_V_MIN], np.uint8)
        hi_pink = np.array([POVEI_COLOR_PINK_H_HI, 255, 255], np.uint8)

        for best_val, cx, cy in candidates:
            # Пропускаем позиции в cooldown/dead-zone
            if exclude_positions and any(
                abs(cx - ex) < CLICK_RADIUS and abs(cy - ey) < CLICK_RADIUS
                for ex, ey, *_ in exclude_positions
            ):
                self._log(f"Povei ({cx},{cy}) conf={best_val:.3f} — cooldown/dead-zone skip")
                continue

            # Пропускаем позиции в перманентном бане (UI-элементы ложно матчащиеся на повей)
            perm_key = (cx // 30, cy // 30)
            if hasattr(self, '_perm_reject_pos') and perm_key in self._perm_reject_pos:
                self._log(f"Povei ({cx},{cy}) conf={best_val:.3f} — PERM BANNED (fake UI element)")
                continue

            # Пропускаем позиции в color-reject зоне (малый радиус, короткий срок)
            if color_reject_zones and any(
                abs(cx - rx) < COLOR_REJECT_RADIUS and abs(cy - ry) < COLOR_REJECT_RADIUS
                for rx, ry, *_ in color_reject_zones
            ):
                self._log(f"Povei ({cx},{cy}) conf={best_val:.3f} — color-reject-zone skip")
                continue

            # Пропускаем занятые ресурсы (жёлтая цифра под ресурсом)
            if self._is_occupied(screenshot, cx, cy):
                self._log(f"Povei ({cx},{cy}) conf={best_val:.3f} — OCCUPIED (yellow digit), skipping")
                continue

            # Цветовая верификация — пропускаем если conf очень высокий (шаблон совпал надёжно)
            vx1 = max(0, cx - verify_half)
            vy1 = max(0, cy - verify_half)
            vx2 = min(sw, cx + verify_half)
            vy2 = min(sh, cy + verify_half)
            verify_patch = screenshot[vy1:vy2, vx1:vx2]
            if verify_patch.size > 0:
                hsv_v = cv2.cvtColor(verify_patch, cv2.COLOR_BGR2HSV)
                dark_px = int(np.sum(cv2.inRange(hsv_v, lo_dark, hi_dark) > 0))
                pink_px = int(np.sum(cv2.inRange(hsv_v, lo_pink, hi_pink) > 0))
                self._log(f"Povei ({cx},{cy}) conf={best_val:.3f} color dark={dark_px} pink={pink_px}")
                # At >=0.95 with any color pixels present, trust the template match.
                # Note: false grass matches at 0.91-0.94 reliably show dark=0 pink=0.
                # Real povei at >=0.95 should have at least 1 dark OR 1 pink pixel.
                if best_val >= 0.95 and (dark_px >= 1 or pink_px >= 1):
                    self._log(f"Povei ({cx},{cy}) conf={best_val:.3f} HIGH CONF color OK — accepted")
                elif dark_px < VERIFY_DARK_MIN and pink_px < VERIFY_PINK_MIN:
                    self._log(f"Povei ({cx},{cy}) conf={best_val:.3f} REJECTED color dark={dark_px} pink={pink_px}")
                    if hasattr(self, '_color_reject_zones'):
                        self._color_reject_zones.append((cx, cy, time.time()))
                    # Счётчик повторных отклонений — после 4 раз позиция уходит в перманентный бан
                    if hasattr(self, '_color_reject_counts'):
                        key = (cx // 30, cy // 30)  # округляем до 30px для группировки
                        self._color_reject_counts[key] = self._color_reject_counts.get(key, 0) + 1
                        if self._color_reject_counts[key] >= 4:
                            if hasattr(self, '_perm_reject_pos'):
                                self._perm_reject_pos.add(key)
                                self._log(f"Povei ({cx},{cy}) → PERMANENTLY BANNED (rejected {self._color_reject_counts[key]}x, key={key})")
                    # Сохраняем debug-патч отклонённой позиции раз в 60 сек
                    now_dbg = time.time()
                    if not hasattr(self, '_last_reject_debug_ts') or now_dbg - self._last_reject_debug_ts > 60.0:
                        self._last_reject_debug_ts = now_dbg
                        try:
                            os.makedirs('debug', exist_ok=True)
                            cv2.imwrite(f'debug/povei_REJECTED_{cx}_{cy}_{int(now_dbg)}.png', verify_patch)
                            self._log(f"  → debug patch saved: debug/povei_REJECTED_{cx}_{cy}_{int(now_dbg)}.png")
                        except Exception:
                            pass
                    continue
                else:
                    self._log(f"Povei ({cx},{cy}) conf={best_val:.3f} color OK dark={dark_px} pink={pink_px}")

            # Кандидат прошёл

            # Сохраняем debug-изображение с найденным кандидатом
            now = time.time()
            if not hasattr(self, '_last_povei_debug_ts') or now - self._last_povei_debug_ts > 20.0:
                self._last_povei_debug_ts = now
                try:
                    os.makedirs('debug', exist_ok=True)
                    dbg = screenshot.copy()
                    cv2.circle(dbg, (cx, cy), 20, (0, 255, 0), 3)
                    cv2.rectangle(dbg, (hx1, hy1), (hx2, hy2), (0, 220, 255), 2)
                    cv2.putText(dbg, f"povei {best_val:.2f}", (cx - 30, cy - 25),
                                cv2.FONT_HERSHEY_SIMPLEX, 0.6, (0, 255, 0), 2)
                    cv2.imwrite(f'debug/povei_found_{int(now)}.png', dbg)
                except Exception:
                    pass

            self._log(f"Povei MATCH: conf={best_val:.3f} pos=({cx},{cy}) tpls={len(povei_tpls)}")
            return (cx, cy), best_val

        self._log(f"Povei: all {len(candidates)} candidate(s) rejected")
        return None, 0.0

    def find_vkusn_match(self, screenshot, exclude_positions=None, fast=False):
        """
        Поиск вкусноцвета только по шаблонам 'vkusnocvet' внутри hunt window (2× downscale).
        Ограничено hunt window чтобы не матчить UI элементы за пределами охоты.
        fast=True — используется при цепочке после ESC, берёт топ-15 шаблонов и 1 масштаб.
        Возвращает (pos, conf, tidx) или (None, 0.0, -1).
        """
        if not self._tpl_cache:
            return None, 0.0, -1

        sh, sw = screenshot.shape[:2]
        # Restrict to hunt window ROI
        hx1 = max(0, self.hunt_left)
        hy1 = max(0, self.hunt_top)
        hx2 = min(sw, sw - self.hunt_right)
        hy2 = min(sh, sh - self.hunt_bottom)
        if hx2 <= hx1 or hy2 <= hy1:
            return None, 0.0, -1
        hunt = screenshot[hy1:hy2, hx1:hx2]

        SCALE_DOWN = 2
        hh, hw = hunt.shape[:2]
        sc_gray, sc_hue, sc_edges = self._preprocess(hunt)

        def dn(img):
            return cv2.resize(img, (max(1, img.shape[1]//SCALE_DOWN),
                                    max(1, img.shape[0]//SCALE_DOWN)),
                              interpolation=cv2.INTER_AREA)
        sm_bgr   = cv2.resize(hunt, (max(1,hw//SCALE_DOWN), max(1,hh//SCALE_DOWN)),
                              interpolation=cv2.INTER_AREA)
        sm_gray  = dn(sc_gray)
        sm_hue   = dn(sc_hue)
        sm_edges = dn(sc_edges)

        best_pos  = None
        best_conf = 0.0
        best_tidx = -1

        # В fast-режиме: только 1 масштаб и топ-15 шаблонов (для быстрого перехода после ESC)
        scale_factors = [1.0] if fast else [0.90, 1.0, 1.10]
        tpl_list = list(enumerate(self._tpl_cache))
        if fast:
            tpl_list = [(i, tc) for i, tc in tpl_list if tc.get('label') != 'povei'][:15]

        deadline_tpl = time.time() + (5.0 if fast else 12.0)  # таймаут поиска

        for tidx, tc in tpl_list:
            if not self.running:
                break
            if time.time() > deadline_tpl:
                self._log("find_vkusn_match: timeout — returning best so far")
                break
            if tc.get('label') == 'povei':
                continue  # повей ищем отдельно
            th, tw = tc['bgr'].shape[:2]
            for sc_factor in scale_factors:
                nw = max(4, int(tw * sc_factor // SCALE_DOWN))
                nh = max(4, int(th * sc_factor // SCALE_DOWN))
                if nw >= sm_bgr.shape[1] or nh >= sm_bgr.shape[0]:
                    continue
                def rs(img, _nw=nw, _nh=nh):
                    return cv2.resize(img, (_nw, _nh), interpolation=cv2.INTER_AREA)
                scores = []
                for (src, tpl, w) in [
                    (sm_bgr,   rs(tc['bgr']),   0.25),
                    (sm_gray,  rs(tc['gray']),  0.25),
                    (sm_hue,   rs(tc['hue']),   0.35),
                    (sm_edges, rs(tc['edges']), 0.15),
                ]:
                    if tpl.shape[0] >= src.shape[0] or tpl.shape[1] >= src.shape[1]:
                        continue
                    try:
                        res = cv2.matchTemplate(src, tpl, cv2.TM_CCOEFF_NORMED)
                        scores.append((res, w))
                    except cv2.error:
                        pass
                if not scores:
                    continue
                min_h = min(r.shape[0] for r,_ in scores)
                min_w = min(r.shape[1] for r,_ in scores)
                combined = sum(r[:min_h,:min_w] * w for r,w in scores)
                combined /= sum(w for _,w in scores)

                _, mx_val, _, mx_loc = cv2.minMaxLoc(combined)
                if mx_val < MATCH_THRESHOLD or mx_val <= best_conf:
                    continue
                # Convert from hunt-local (downscaled) coords to full-screenshot coords
                cx = mx_loc[0] * SCALE_DOWN + int(tw * sc_factor) // 2 + hx1
                cy = mx_loc[1] * SCALE_DOWN + int(th * sc_factor) // 2 + hy1
                if exclude_positions and any(
                    abs(cx - ex) < CLICK_RADIUS and abs(cy - ey) < CLICK_RADIUS
                    for ex, ey, *_ in exclude_positions
                ):
                    continue
                # Color verify
                vx1 = max(0, cx - 36); vx2 = min(sw, cx + 36)
                vy1 = max(0, cy - 36); vy2 = min(sh, cy + 36)
                v_patch = screenshot[vy1:vy2, vx1:vx2]
                if v_patch.size > 0:
                    v_hsv = cv2.cvtColor(v_patch, cv2.COLOR_BGR2HSV)
                    v_h, v_s, _ = cv2.split(v_hsv)
                    v_px = int(np.sum((v_h >= COLOR_H_LO) & (v_h <= COLOR_H_HI) & (v_s >= COLOR_S_MIN)))
                    if v_px < 10:
                        continue
                if self._is_occupied(screenshot, cx, cy):
                    continue
                best_conf = mx_val
                best_pos  = (cx, cy)
                best_tidx = tidx
                if best_conf > 0.70:
                    return best_pos, best_conf, best_tidx

        return best_pos, best_conf, best_tidx

    def find_best_match(self, screenshot, exclude_positions=None):
        """Обёртка для обратной совместимости (scan_povei_once и др.)."""
        # Сначала повей
        ppos, pconf = self.find_povei_match(screenshot, exclude_positions, None)
        if ppos is not None:
            # Найти tidx повея
            for i, tc in enumerate(self._tpl_cache):
                if tc.get('label') == 'povei':
                    return ppos, pconf, i
        # Потом вкусноцвет
        return self.find_vkusn_match(screenshot, exclude_positions)

    # ── screenshot ──────────────────────────────────────────────────────────────

    def _grab_screenshot(self):
        try:
            with mss() as sct:
                mon = {
                    'left':   self.capture_bounds['x'],
                    'top':    self.capture_bounds['y'],
                    'width':  self.capture_bounds['width'],
                    'height': self.capture_bounds['height'],
                }
                shot = sct.grab(mon)
                return cv2.cvtColor(np.array(shot), cv2.COLOR_BGRA2BGR)
        except Exception as e:
            self._log(f"Screenshot error: {e}")
            return None

    # ── mouse move and clicks ───────────────────────────────────────────────────

    def _move_to(self, x, y, duration=0.0):
        if self.dry_run:
            self._log(f"DRY moveTo({x},{y})")
            return
        try:
            if self._is_windows:
                ctypes.windll.user32.SetCursorPos(int(x), int(y))
                pos = pyautogui.position()
                if abs(pos.x - x) > 5 or abs(pos.y - y) > 5:
                    pyautogui.moveTo(x, y, duration=0.05)
            else:
                pyautogui.moveTo(x, y, duration=duration)
        except Exception as e:
            self._log(f"moveTo error: {e}")

    def _click(self):
        if self.dry_run:
            self._log("DRY click()")
            return
        try:
            if self._is_windows:
                ctypes.windll.user32.mouse_event(0x0002, 0, 0, 0, 0)
                time.sleep(0.05)
                ctypes.windll.user32.mouse_event(0x0004, 0, 0, 0, 0)
            else:
                pyautogui.click()
        except Exception as e:
            self._log(f"click error: {e}")

    def _dbl_click(self):
        self._click()
        time.sleep(0.12)
        self._click()

    # ── sweep (disabled in auto mode, kept for debug) ───────────────────────────

    def _init_sweep(self):
        pass  # sweep disabled — cursor stays still

    def _sweep_move(self):
        pass  # sweep disabled — cursor stays still

    # ── RECORD MODE ─────────────────────────────────────────────────────────────

    def start_recording(self):
        self.running = True
        _last_scan_ts  = [0.0]   # время последнего полного скана
        _last_scan_shot = [None]  # кэш последнего скриншота для детектора
        SCAN_INTERVAL  = 0.4     # секунды между полными сканами

        def _get_scan_shot():
            """Возвращает кэшированный скриншот (обновляется каждые SCAN_INTERVAL сек)."""
            now = time.time()
            if now - _last_scan_ts[0] >= SCAN_INTERVAL:
                _last_scan_ts[0]  = now
                _last_scan_shot[0] = self._grab_screenshot()
            return _last_scan_shot[0]

        def _score_at(px, py, shot):
            """
            Быстрый цветовой скор в патче вокруг (px, py).
            Возвращает (label, score_0_to_1) или (None, 0).
            """
            if shot is None:
                return None, 0.0
            h, w = shot.shape[:2]
            half = CROP_HALF
            x1 = max(0, px - half); x2 = min(w, px + half)
            y1 = max(0, py - half); y2 = min(h, py + half)
            patch = shot[y1:y2, x1:x2]
            if patch.size == 0:
                return None, 0.0
            hsv = cv2.cvtColor(patch, cv2.COLOR_BGR2HSV)

            # Повей: тёмно-бордово (#430006) + розовый (#E33789)
            lo_dark = np.array([POVEI_COLOR_DARK_H_LO, POVEI_COLOR_DARK_S_MIN, POVEI_COLOR_DARK_V_MIN], np.uint8)
            hi_dark = np.array([POVEI_COLOR_DARK_H_HI, 255, POVEI_COLOR_DARK_V_MAX], np.uint8)
            lo_pink = np.array([POVEI_COLOR_PINK_H_LO, POVEI_COLOR_PINK_S_MIN, POVEI_COLOR_PINK_V_MIN], np.uint8)
            hi_pink = np.array([POVEI_COLOR_PINK_H_HI, 255, 255], np.uint8)
            dark_px = int(np.sum(cv2.inRange(hsv, lo_dark, hi_dark) > 0))
            pink_px = int(np.sum(cv2.inRange(hsv, lo_pink, hi_pink) > 0))
            povei_score = dark_px * 2 + pink_px

            # Вкусноцвет: пурпурный/малиновый H=130..175
            lo_v1 = np.array([COLOR_H_LO, COLOR_S_MIN, COLOR_V_MIN], np.uint8)
            hi_v1 = np.array([COLOR_H_HI, 255, COLOR_V_MAX], np.uint8)
            vkusn_px = int(np.sum(cv2.inRange(hsv, lo_v1, hi_v1) > 0))

            if povei_score >= 4 and povei_score >= vkusn_px:
                conf = min(0.99, povei_score / 20.0)
                return 'povei', conf
            elif vkusn_px >= 4:
                conf = min(0.99, vkusn_px / 30.0)
                return 'vkusnocvet', conf
            elif povei_score >= 2:
                conf = min(0.5, povei_score / 20.0)
                return 'povei', conf
            return None, 0.0

        def on_move(x, y):
            cb = self.cursor_bounds
            if not (cb['x'] <= x <= cb['x'] + cb['width'] and
                    cb['y'] <= y <= cb['y'] + cb['height']):
                return
            lx = x - cb['x']
            ly = y - cb['y']
            now = time.time()
            if (now - self._last_emit_ts) >= 0.05 and (
                    abs(lx - self._last_emit_pos[0]) >= 2 or
                    abs(ly - self._last_emit_pos[1]) >= 2):
                px = int(round(lx * self.scale))
                py = int(round(ly * self.scale))

                # Быстрый цветовой детектор — подсветка типа ресурса под курсором
                shot = _get_scan_shot()
                det_label, det_conf = _score_at(px, py, shot)
                if det_label == 'povei':
                    conf_pct = int(det_conf * 100)
                    self._emit(f"SHOW_SQUARE:{px},{py},povei_scan_{conf_pct}")
                elif det_label == 'vkusnocvet':
                    conf_pct = int(det_conf * 100)
                    self._emit(f"SHOW_SQUARE:{px},{py},vkusn_scan_{conf_pct}")
                else:
                    self._emit(f"SHOW_SQUARE:{px},{py},Cursor")

                self._last_emit_ts  = now
                self._last_emit_pos = (lx, ly)

        def on_click(x, y, button, pressed):
            if not pressed or button != mouse.Button.left:
                return
            cb = self.cursor_bounds
            if not (cb['x'] <= x <= cb['x'] + cb['width'] and
                    cb['y'] <= y <= cb['y'] + cb['height']):
                return
            lx = x - cb['x']
            ly = y - cb['y']
            px = int(round(lx * self.scale))
            py = int(round(ly * self.scale))
            self._log(f"CLICK at ({lx:.0f},{ly:.0f})")
            self._emit("HIDE_SQUARE")
            # Скриншот ДО паузы — прицел ещё не появился в игре
            pre_shot = self._grab_screenshot()
            time.sleep(0.08)
            self._save_sample(px, py, pre_shot=pre_shot)
            # Подсветка цвета зависит от метки: повей=зелёный, вкусноцвет=пурпурный
            saved_label = self.record_label if self.record_label in ('povei', 'vkusnocvet') else 'Saved'
            self._emit(f"SHOW_SQUARE:{px},{py},{saved_label}")

        listener = mouse.Listener(on_move=on_move, on_click=on_click)
        listener.start()
        try:
            while self.running:
                self._sleep(0.1)
        except KeyboardInterrupt:
            pass
        finally:
            listener.stop()
            if not self._saved_on_exit:
                self.save_all_samples()
                self._saved_on_exit = True

    def _remove_crosshair(self, img):
        """
        Убирает прицел (тёмный крест в центре патча) методом cv2.inpaint.
        Прицел появляется в игре через несколько кадров после клика —
        но на случай если скриншот чуть запоздал, чистим его здесь.
        Возвращает очищенное изображение.
        """
        h, w = img.shape[:2]
        cx, cy = w // 2, h // 2
        gray = cv2.cvtColor(img, cv2.COLOR_BGR2GRAY)
        mask = np.zeros((h, w), dtype=np.uint8)
        r = 7  # радиус поиска прицела вокруг центра
        for y in range(max(0, cy - r), min(h, cy + r + 1)):
            for x in range(max(0, cx - r), min(w, cx + r + 1)):
                if gray[y, x] < 60:   # тёмный пиксель = часть прицела
                    mask[y, x] = 255
        if np.sum(mask) == 0:
            return img   # прицела нет — возвращаем как есть
        return cv2.inpaint(img, mask, 4, cv2.INPAINT_TELEA)

    def _save_sample(self, px, py, pre_shot=None):
        # Используем pre_shot (без прицела) или делаем новый скриншот
        shot = pre_shot if pre_shot is not None else self._grab_screenshot()
        if shot is None:
            self._log("ERROR: could not grab screenshot for sample")
            return

        label = self.record_label
        # Повей — маленькая иконка, нужен меньший патч
        half = POVEI_CROP_HALF if label == 'povei' else CROP_HALF

        x1 = max(0, px - half)
        y1 = max(0, py - half)
        x2 = min(shot.shape[1], px + half)
        y2 = min(shot.shape[0], py + half)
        crop = shot[y1:y2, x1:x2]

        # Убираем прицел из центра патча на случай если скриншот чуть запоздал
        crop = self._remove_crosshair(crop)

        if label and label not in ('recorded',):
            save_dir = os.path.join('training_data', label)
        else:
            save_dir = 'training_data'
        os.makedirs(save_dir, exist_ok=True)

        sid  = len(self.recorded_samples)
        path = os.path.join(save_dir, f"sample_{sid}.png").replace('\\', '/')
        cv2.imwrite(path, crop)
        entry = {'x': px, 'y': py, 'image': path, 'width': x2 - x1, 'height': y2 - y1,
                 'label': label}
        self.recorded_samples.append(entry)
        self.sample_templates.append(crop.copy())
        # Предобрабатываем шаблон и добавляем в кэш
        mask    = self._make_fg_mask(crop)
        gray_eq, hue, edges = self._preprocess(crop)
        self._tpl_cache.append({
            'bgr':   crop,
            'gray':  gray_eq,
            'hue':   cv2.bitwise_and(hue, hue, mask=mask),
            'edges': cv2.bitwise_and(edges, edges, mask=mask),
            'mask':  mask,
            'label': label,
            'image': path,
        })
        n_label = sum(1 for tc in self._tpl_cache if tc['label'] == label)
        self._log(f"SAVED sample_{sid}.png  pos=({px},{py}) size={x2-x1}x{y2-y1} label={label} ({n_label} total)")

        if label == 'povei':
            n = self._update_povei_thresholds_live(save_dir)
            self._emit(f"POVEI_SAMPLE_SAVED:{n}")

    def _update_povei_thresholds_live(self, povei_dir):
        try:
            files = [f for f in os.listdir(povei_dir) if f.endswith('.png')]
            n = len(files)
            self._log(f"Povei templates: {n} samples in {povei_dir}")
            return n
        except Exception:
            return 0

    def _save_confirmed_sample(self, px, py, label, pre_shot=None):
        """
        Автоматически сохраняет патч при подтверждённой добыче (HIT+confirmed).
        pre_shot — скриншот ДО клика (без прицела). Если None — делает новый.
        Сохраняет в training_data/<label>/ и добавляет в кэш шаблонов.
        Ограничение: не более 1 сэмпла за 60 сек с одной позиции (чтобы не спамить).
        """
        now = time.time()
        # Проверяем — не сохраняли ли уже недавно рядом с этой позицией
        if not hasattr(self, '_confirmed_save_log'):
            self._confirmed_save_log = []  # list of (px, py, ts)
        # Чистим старые записи старше 60 сек
        self._confirmed_save_log = [(sx, sy, st) for sx, sy, st in self._confirmed_save_log
                                     if now - st < 60.0]
        # Проверяем дубль
        if any(abs(px - sx) < CLICK_RADIUS and abs(py - sy) < CLICK_RADIUS
               for sx, sy, _ in self._confirmed_save_log):
            self._log(f"[auto-save] Skipped duplicate confirmed sample at ({px},{py})")
            return

        # Используем pre_shot (без прицела) или делаем новый скриншот
        shot = pre_shot if pre_shot is not None else self._grab_screenshot()
        if shot is None:
            return

        # Определяем папку и размер патча
        if label in ('povei', 'vkusnocvet'):
            save_dir = os.path.join('training_data', label)
        else:
            return  # blob/unknown — не сохраняем
        os.makedirs(save_dir, exist_ok=True)

        half = POVEI_CROP_HALF if label == 'povei' else CROP_HALF
        x1 = max(0, px - half)
        y1 = max(0, py - half)
        x2 = min(shot.shape[1], px + half)
        y2 = min(shot.shape[0], py + half)
        crop = shot[y1:y2, x1:x2]
        if crop.size == 0:
            return

        # Генерируем уникальное имя файла
        existing = [f for f in os.listdir(save_dir) if f.endswith('.png')]
        nums = []
        for f in existing:
            base = os.path.splitext(f)[0]
            num = base.split('_')[-1]
            if num.isdigit():
                nums.append(int(num))
        next_id = (max(nums) + 1) if nums else 0
        path = os.path.join(save_dir, f"sample_{next_id}.png").replace('\\', '/')
        cv2.imwrite(path, crop)

        # Добавляем в кэш шаблонов сразу (без перезагрузки)
        mask    = self._make_fg_mask(crop)
        gray_eq, hue, edges = self._preprocess(crop)
        self._tpl_cache.append({
            'bgr':   crop,
            'gray':  gray_eq,
            'hue':   cv2.bitwise_and(hue, hue, mask=mask),
            'edges': cv2.bitwise_and(edges, edges, mask=mask),
            'mask':  mask,
            'label': label,
            'image': path,
        })
        self._confirmed_save_log.append((px, py, now))
        self._log(f"[auto-save] Confirmed {label} sample saved: {path}  cache={len(self._tpl_cache)} tpls")

    def _save_false_positive_sample(self, px, py, label, shot):
        """
        Автоматически сохраняет патч при ложном срабатывании (false positive).
        Ложные срабатывания сохраняются в отдельную папку для анализа и минус-примеров.
        shot — скриншот ДО клика (без прицела).
        Ограничение: не более 1 сэмпла за 120 сек с одной позиции (чтобы не спамить).
        """
        now = time.time()
        # Проверяем — не сохраняли ли уже недавно рядом с этой позицией
        if not hasattr(self, '_false_positive_log'):
            self._false_positive_log = []  # list of (px, py, ts)
        # Чистим старые записи старше 120 сек
        self._false_positive_log = [(sx, sy, st) for sx, sy, st in self._false_positive_log
                                    if now - st < 120.0]
        # Проверяем дубль
        if any(abs(px - sx) < CLICK_RADIUS and abs(py - sy) < CLICK_RADIUS
               for sx, sy, _ in self._false_positive_log):
            return

        if shot is None:
            return

        # Определяем папку для сохранения false positive сэмплов
        if label in ('povei', 'vkusnocvet'):
            save_dir = os.path.join('training_data', f'{label}_false_positive')
        else:
            return  # неизвестный тип — не сохраняем
        os.makedirs(save_dir, exist_ok=True)

        half = POVEI_CROP_HALF if label == 'povei' else CROP_HALF
        x1 = max(0, px - half)
        y1 = max(0, py - half)
        x2 = min(shot.shape[1], px + half)
        y2 = min(shot.shape[0], py + half)
        crop = shot[y1:y2, x1:x2]
        if crop.size == 0:
            return

        # Генерируем уникальное имя файла
        existing = [f for f in os.listdir(save_dir) if f.endswith('.png')]
        nums = []
        for f in existing:
            base = os.path.splitext(f)[0]
            num = base.split('_')[-1]
            if num.isdigit():
                nums.append(int(num))
        next_id = (max(nums) + 1) if nums else 0
        path = os.path.join(save_dir, f"false_pos_{next_id}.png").replace('\\', '/')
        cv2.imwrite(path, crop)

        self._false_positive_log.append((px, py, now))
        self._log(f"[fp-save] False positive {label} sample saved: {path}")

    def save_all_samples(self):
        with open('recorded_samples.json', 'w', encoding='utf-8') as f:
            json.dump(self.recorded_samples, f, indent=2, ensure_ascii=False)
        self._log(f"SAVED {len(self.recorded_samples)} samples to recorded_samples.json")

    def stop(self):
        self.running = False


# ─── main ───────────────────────────────────────────────────────────────────────

if __name__ == '__main__':
    ap = argparse.ArgumentParser()
    ap.add_argument('--record',         action='store_true')
    ap.add_argument('--capture-x',      type=int,   default=None)
    ap.add_argument('--capture-y',      type=int,   default=None)
    ap.add_argument('--capture-width',  type=int,   default=None)
    ap.add_argument('--capture-height', type=int,   default=None)
    ap.add_argument('--cursor-x',       type=int,   default=None)
    ap.add_argument('--cursor-y',       type=int,   default=None)
    ap.add_argument('--cursor-width',   type=int,   default=None)
    ap.add_argument('--cursor-height',  type=int,   default=None)
    ap.add_argument('--window-x',       type=int,   default=0)
    ap.add_argument('--window-y',       type=int,   default=0)
    ap.add_argument('--window-width',   type=int,   default=1920)
    ap.add_argument('--window-height',  type=int,   default=1080)
    ap.add_argument('--scale',          type=float, default=1.0)
    ap.add_argument('--stop-token',     type=str,   default='')
    ap.add_argument('--max-cycles',     type=int,   default=0)
    ap.add_argument('--dry-run',        action='store_true')
    ap.add_argument('--record-label',   type=str,   default='recorded',
                    help='Label for recorded samples (e.g. povei, vkusnocvet)')
    ap.add_argument('--scan-povei',     action='store_true',
                    help='One-shot povei scan diagnostic — grabs screenshot, runs detector, saves debug images')
    ap.add_argument('--analyze-povei',  action='store_true',
                    help='Analyze HSV colors in training_data/povei/ and update adaptive thresholds')
    ap.add_argument('--hunt-left',      type=int, default=None,
                    help='Hunt window left margin in physical px (overrides default)')
    ap.add_argument('--hunt-top',       type=int, default=None,
                    help='Hunt window top margin in physical px (overrides default)')
    ap.add_argument('--hunt-right',     type=int, default=None,
                    help='Hunt window right margin in physical px (overrides default)')
    ap.add_argument('--hunt-bottom',    type=int, default=None,
                    help='Hunt window bottom margin in physical px (overrides default)')
    args = ap.parse_args()

    capture_bounds = {
        'x':      args.capture_x      if args.capture_x      is not None else args.window_x,
        'y':      args.capture_y      if args.capture_y      is not None else args.window_y,
        'width':  args.capture_width  if args.capture_width  is not None else args.window_width,
        'height': args.capture_height if args.capture_height is not None else args.window_height,
    }
    cursor_bounds = {
        'x':      args.cursor_x      if args.cursor_x      is not None else args.window_x,
        'y':      args.cursor_y      if args.cursor_y      is not None else args.window_y,
        'width':  args.cursor_width  if args.cursor_width  is not None else args.window_width,
        'height': args.cursor_height if args.cursor_height is not None else args.window_height,
    }

    # ── Diagnostic modes (no bot loop) ──────────────────────────────────────────
    if getattr(args, 'analyze_povei', False):
        DwarBot.analyze_povei_colors_from_samples()
        sys.exit(0)

    if getattr(args, 'scan_povei', False):
        bot = DwarBot(
            record_mode    = False,
            capture_bounds = capture_bounds,
            cursor_bounds  = cursor_bounds,
            scale          = args.scale,
            hunt_left      = args.hunt_left,
            hunt_top       = args.hunt_top,
            hunt_right     = args.hunt_right,
            hunt_bottom    = args.hunt_bottom,
        )
        bot.scan_povei_once()
        sys.exit(0)

    bot = DwarBot(
        record_mode    = args.record,
        capture_bounds = capture_bounds,
        cursor_bounds  = cursor_bounds,
        scale          = args.scale,
        stop_token     = args.stop_token,
        max_cycles     = args.max_cycles,
        dry_run        = args.dry_run,
        record_label   = args.record_label,
        hunt_left      = args.hunt_left,
        hunt_top       = args.hunt_top,
        hunt_right     = args.hunt_right,
        hunt_bottom    = args.hunt_bottom,
    )

    try:
        bot.start()
    except KeyboardInterrupt:
        bot.stop()
