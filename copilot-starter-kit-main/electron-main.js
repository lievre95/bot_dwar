const { app, BrowserWindow, ipcMain, screen, globalShortcut } = require('electron');
const { spawn, execSync } = require('child_process');
const path = require('path');
const fs   = require('fs');

let gameWindow;
let controlWindow;
let botProcess;
let markerProcess;
let captureScale = 1;
let botStopToken = null;
let markerStopToken = null;

// ── Hunt ROI settings (physical px margins from capture edges) ───────────────
const ROI_CONFIG_PATH = path.join(__dirname, 'config', 'hunt-roi.json');
let huntROI = { left: 80, top: 200, right: 580, bottom: 180 };

function loadHuntROI() {
  try {
    if (fs.existsSync(ROI_CONFIG_PATH)) {
      const data = JSON.parse(fs.readFileSync(ROI_CONFIG_PATH, 'utf8'));
      if (typeof data.left === 'number') huntROI = data;
      console.log(`Hunt ROI loaded: L=${huntROI.left} T=${huntROI.top} R=${huntROI.right} B=${huntROI.bottom}`);
    }
  } catch (e) {
    console.error('loadHuntROI error:', e);
  }
}

function saveHuntROI() {
  try {
    fs.mkdirSync(path.join(__dirname, 'config'), { recursive: true });
    fs.writeFileSync(ROI_CONFIG_PATH, JSON.stringify(huntROI, null, 2), 'utf8');
  } catch (e) {
    console.error('saveHuntROI error:', e);
  }
}

// ── Chat ROI settings ────────────────────────────────────────────────────────
const CHAT_ROI_CONFIG_PATH = path.join(__dirname, 'config', 'chat-roi.json');
let chatROI = { left: 0, top: 0, right: 0, bottom: 0 };

function loadChatROI() {
  try {
    if (fs.existsSync(CHAT_ROI_CONFIG_PATH)) {
      const data = JSON.parse(fs.readFileSync(CHAT_ROI_CONFIG_PATH, 'utf8'));
      if (typeof data.left === 'number') chatROI = data;
      console.log(`Chat ROI loaded: L=${chatROI.left} T=${chatROI.top} R=${chatROI.right} B=${chatROI.bottom}`);
    }
  } catch (e) {
    console.error('loadChatROI error:', e);
  }
}

function saveChatROI() {
  try {
    fs.mkdirSync(path.join(__dirname, 'config'), { recursive: true });
    fs.writeFileSync(CHAT_ROI_CONFIG_PATH, JSON.stringify(chatROI, null, 2), 'utf8');
  } catch (e) {
    console.error('saveChatROI error:', e);
  }
}

loadHuntROI();
loadChatROI();

// ── auto-detect Python 3 ────────────────────────────────────────────────────
function findPython() {
  const candidates = [
    'C:\\Users\\ivand\\AppData\\Local\\Programs\\Python\\Python311\\python.exe',
    'C:\\Python311\\python.exe',
    'C:\\Python310\\python.exe',
    'C:\\Python39\\python.exe',
  ];
  for (const p of candidates) {
    try {
      const fs = require('fs');
      if (fs.existsSync(p)) return p;
    } catch {}
  }
  // fallback: try PATH
  try { execSync('python --version'); return 'python'; } catch {}
  try { execSync('python3 --version'); return 'python3'; } catch {}
  throw new Error('Python not found! Install Python 3.9+ and check the path in electron-main.js');
}

const PYTHON = findPython();
console.log(`Using Python: ${PYTHON}`);

function createWindows() {

  // Находим монитор 2560x1440 (основной), или самый большой
  const displays = screen.getAllDisplays();

  // Логируем все доступные дисплеи
  console.log(`Available displays: ${displays.length}`);
  displays.forEach((d, i) => {
    console.log(`  Display ${i}: ${d.bounds.width}x${d.bounds.height} at (${d.bounds.x}, ${d.bounds.y})`);
  });

  // Сначала ищем 2560x1440
  let largestDisplay = displays.find(d => d.bounds.width === 2560 && d.bounds.height === 1440);

  // Если не найдена 2560x1440, ищем 3440x1440 (ultrawide)
  if (!largestDisplay) {
    largestDisplay = displays.find(d => d.bounds.width === 3440 && d.bounds.height === 1440);
  }

  // Если ничего не найдено, выбираем самый большой монитор
  if (!largestDisplay) {
    let maxArea = 0;
    for (const display of displays) {
      const area = display.bounds.width * display.bounds.height;
      if (area > maxArea) {
        maxArea = area;
        largestDisplay = display;
      }
    }
  }

  console.log(`Using display: ${largestDisplay.bounds.width}x${largestDisplay.bounds.height} at (${largestDisplay.bounds.x}, ${largestDisplay.bounds.y})`);

  // Главное окно - браузер с игрой (максимизированное на выбранном дисплее)
  gameWindow = new BrowserWindow({
    width: largestDisplay.bounds.width - 100,
    height: largestDisplay.bounds.height - 100,
    x: largestDisplay.bounds.x + 50,
    y: largestDisplay.bounds.y + 50,
    webPreferences: {
      nodeIntegration: false,
      contextIsolation: true,
      sandbox: true,
      webSecurity: true,
      userAgent: 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/131.0.0.0 Safari/537.36'
    }
  });

  // Максимизируем окно при запуске
  gameWindow.maximize();

  // Устанавливаем реальные заголовки
  gameWindow.webContents.session.webRequest.onBeforeSendHeaders((details, callback) => {
    details.requestHeaders['Accept-Language'] = 'ru-RU,ru;q=0.9,en-US;q=0.8,en;q=0.7';
    details.requestHeaders['sec-ch-ua'] = '"Google Chrome";v="131", "Chromium";v="131", "Not_A Brand";v="24"';
    details.requestHeaders['sec-ch-ua-mobile'] = '?0';
    details.requestHeaders['sec-ch-ua-platform'] = '"Windows"';
    callback({ requestHeaders: details.requestHeaders });
  });

  gameWindow.loadURL('https://dwar.ru');

  // Overlay окно управления (всегда поверх)
  controlWindow = new BrowserWindow({
    width: 310,
    height: 560,
    frame: false,
    transparent: true,
    alwaysOnTop: true,
    resizable: false,
    skipTaskbar: true,
    webPreferences: {
      nodeIntegration: true,
      contextIsolation: false
    }
  });

  controlWindow.loadFile('control.html');

  // Позиционируем в правом верхнем углу главного монитора
  const { width } = screen.getPrimaryDisplay().workAreaSize;
  controlWindow.setPosition(width - 320, 20);
}

function getCaptureArgs(includeRecord = false) {
  // ВАЖНО: contentBounds в logical px
  const content = gameWindow.getContentBounds();
  const display = screen.getDisplayNearestPoint({ x: content.x, y: content.y });
  captureScale = display.scaleFactor || 1;

  // Для mss нужны physical px
  const px = {
    x: Math.round(content.x * captureScale),
    y: Math.round(content.y * captureScale),
    width: Math.round(content.width * captureScale),
    height: Math.round(content.height * captureScale)
  };

  const args = [
    '--capture-x', String(px.x),
    '--capture-y', String(px.y),
    '--capture-width', String(px.width),
    '--capture-height', String(px.height),
    '--cursor-x', String(content.x),
    '--cursor-y', String(content.y),
    '--cursor-width', String(content.width),
    '--cursor-height', String(content.height),
    '--scale', String(captureScale),
    '--hunt-left',   String(Math.round(huntROI.left   * captureScale)),
    '--hunt-top',    String(Math.round(huntROI.top    * captureScale)),
    '--hunt-right',  String(Math.round(huntROI.right  * captureScale)),
    '--hunt-bottom', String(Math.round(huntROI.bottom * captureScale)),
  ];

  if (includeRecord) {
    args.unshift('--record');
  }

  console.log(`Capture bounds(px): ${px.x},${px.y} ${px.width}x${px.height}, scale=${captureScale}`);
  console.log(`Hunt ROI (logical): L=${huntROI.left} T=${huntROI.top} R=${huntROI.right} B=${huntROI.bottom}`);
  return args;
}

function wireBotProcess(proc, tag) {
  proc.stdout.on('data', (data) => {
    const output = data.toString();
    // Обрабатываем построчно, чтобы не терять несколько SHOW_SQUARE в одном чанке
    output.split(/\r?\n/).forEach((line) => {
      const trimmed = line.trim();
      if (!trimmed) return;
      console.log(`${tag}: ${trimmed}`);

      if (trimmed.startsWith('SHOW_SQUARE:')) {
        const match = trimmed.match(/^SHOW_SQUARE:(\d+),(\d+),(.+)$/);
        if (match) {
          showAttentionSquare(parseInt(match[1], 10), parseInt(match[2], 10), match[3].trim());
        }
      }

      if (trimmed.startsWith('SHOW_CANDIDATES:')) {
        const payload = trimmed.slice('SHOW_CANDIDATES:'.length);
        const items = payload.split('|').map(p => {
          const [x, y, label, conf] = p.split(',');
          return { x: parseInt(x, 10), y: parseInt(y, 10), label, conf: parseFloat(conf) };
        }).filter(i => !isNaN(i.x));
        showCandidateMarkers(items);
      }

      if (trimmed === 'HIDE_SQUARE') {
        hideAttentionSquare();
      }

      if (trimmed === 'HIDE_CANDIDATES') {
        hideCandidateMarkers();
      }

      if (trimmed.startsWith('SHOW_HUNT_ROI:')) {
        const parts = trimmed.slice('SHOW_HUNT_ROI:'.length).split(',').map(Number);
        if (parts.length === 4) showHuntROI(...parts);
      }

      if (trimmed === 'PROVERKA_DETECTED') {
        if (controlWindow && !controlWindow.isDestroyed()) {
          controlWindow.webContents.send('proverka-detected');
        }
      }

      if (trimmed === 'NEUDACHA_DETECTED') {
        if (controlWindow && !controlWindow.isDestroyed()) {
          controlWindow.webContents.send('bot-log', '⚠️ НЕУДАЧА — закрываю окно...\n');
        }
      }

      if (trimmed === 'NEUDACHA_CLOSED') {
        if (controlWindow && !controlWindow.isDestroyed()) {
          controlWindow.webContents.send('bot-log', '✅ Окно неудачи закрыто — продолжаю поиск\n');
        }
      }

      if (trimmed === 'BOI_DETECTED') {
        if (controlWindow && !controlWindow.isDestroyed()) {
          controlWindow.webContents.send('bot-log', '⚔️ БОЙ — поиск ресурсов приостановлен\n');
        }
      }

      if (trimmed === 'BOI_GONE') {
        if (controlWindow && !controlWindow.isDestroyed()) {
          controlWindow.webContents.send('bot-log', '✅ Бой завершён — возобновляю поиск\n');
        }
      }

      if (trimmed.startsWith('RESOURCES:')) {
        const n = parseInt(trimmed.split(':')[1]) || 0;
        if (controlWindow && !controlWindow.isDestroyed()) {
          controlWindow.webContents.send('bot-log', `✅ Ресурс #${n} добыт — ищу следующий\n`);
        }
      }

      if (trimmed.startsWith('HINT_POVEI_SAVED:')) {
        const n = parseInt(trimmed.split(':')[1]) || 0;
        if (controlWindow && !controlWindow.isDestroyed()) {
          controlWindow.webContents.send('hint-povei-saved', { count: n });
        }
      }

      if (trimmed.startsWith('HINT_SAVED:')) {
        const parts = trimmed.slice('HINT_SAVED:'.length).split(',');
        const hlabel = parts[0];
        const n = parseInt(parts[1]) || 0;
        if (controlWindow && !controlWindow.isDestroyed()) {
          controlWindow.webContents.send('hint-saved', { label: hlabel, count: n });
        }
      }

      if (trimmed.startsWith('SCAN_POVEI_RESULT:')) {
        const jsonStr = trimmed.slice('SCAN_POVEI_RESULT:'.length);
        try {
          const data = JSON.parse(jsonStr);
          if (controlWindow && !controlWindow.isDestroyed()) {
            controlWindow.webContents.send('scan-povei-result', data);
          }
        } catch (e) {
          console.error('SCAN_POVEI_RESULT parse error:', e);
        }
      }

      if (trimmed.startsWith('CHAT_GATHERED:')) {
        const lbl = trimmed.split(':')[1] || '';
        const icon = lbl === 'povei' ? '🌿' : '🌸';
        const name = lbl === 'povei' ? 'Повей-трава' : lbl === 'vkusnocvet' ? 'Вкусноцвет' : 'ресурс';
        if (controlWindow && !controlWindow.isDestroyed()) {
          controlWindow.webContents.send('bot-log', `${icon} ЧАТ: получен ${name} → перехожу к следующему\n`);
          controlWindow.webContents.send('chat-gathered', { label: lbl });
        }
      }

      if (trimmed.startsWith('CHAT_TPL_SAVED:')) {
        const parts = trimmed.split(':');
        const lbl = parts[1] || '';
        const n   = parseInt(parts[2]) || 0;
        if (controlWindow && !controlWindow.isDestroyed()) {
          controlWindow.webContents.send('chat-tpl-saved', { label: lbl, count: n });
        }
      }

      if (trimmed.startsWith('SHOW_CHAT_ROI:')) {
        const parts = trimmed.slice('SHOW_CHAT_ROI:'.length).split(',').map(Number);
        if (parts.length === 4) showChatROI(...parts);
      }
    });

    controlWindow.webContents.send('bot-log', output);
  });

  proc.stderr.on('data', (data) => {
    console.error(`Bot Error: ${data}`);
  });

  proc.on('exit', (code, signal) => {
    console.log(`${tag} process exited: code=${code}, signal=${signal}`);
    botProcess = null;
    if (controlWindow && !controlWindow.isDestroyed()) {
      controlWindow.webContents.send('bot-status', { running: false });
    }
  });
}

function hideAttentionSquare() {
  if (gameWindow && !gameWindow.isDestroyed()) {
    gameWindow.webContents.executeJavaScript(`
      (function() {
        const old = document.getElementById('bot-attention-square');
        if (old) old.remove();
      })();
    `);
  }
}

function hideCandidateMarkers() {
  if (gameWindow && !gameWindow.isDestroyed()) {
    gameWindow.webContents.executeJavaScript(
      `document.querySelectorAll('.bot-candidate').forEach(e=>e.remove());`
    ).catch(() => {});
  }
}

ipcMain.on('hide-hunt-roi', () => {
  if (gameWindow && !gameWindow.isDestroyed()) {
    gameWindow.webContents.executeJavaScript(
      `document.getElementById('bot-hunt-roi')?.remove();` +
      `document.querySelectorAll('.bot-candidate').forEach(e=>e.remove());`
    ).catch(() => {});
  }
});

// ── Hunt ROI config IPC ──────────────────────────────────────────────────────
ipcMain.handle('get-hunt-roi', () => huntROI);

// ── Two-point ROI picker ─────────────────────────────────────────────────────
// Inject an overlay into the game window; user clicks two corners of the hunt zone.
// First click = top-left, second click = bottom-right (order doesn't matter — auto-sorted).
ipcMain.on('start-roi-pick', () => {
  if (!gameWindow || gameWindow.isDestroyed()) return;
  console.log('ROI pick started — waiting for 2 clicks in game window');
  if (controlWindow && !controlWindow.isDestroyed()) {
    controlWindow.webContents.send('roi-pick-started');
  }

  gameWindow.webContents.executeJavaScript(`
    (function() {
      // Remove any existing picker
      const oldOverlay = document.getElementById('bot-roi-picker');
      if (oldOverlay) oldOverlay.remove();

      const overlay = document.createElement('div');
      overlay.id = 'bot-roi-picker';
      overlay.style.cssText =
        'position:fixed;left:0;top:0;right:0;bottom:0;'
        + 'z-index:9999999;cursor:crosshair;'
        + 'background:rgba(0,60,120,0.18);';

      const hint = document.createElement('div');
      hint.id = 'bot-roi-hint';
      hint.style.cssText =
        'position:fixed;top:14px;left:50%;transform:translateX(-50%);'
        + 'background:rgba(0,0,0,0.82);color:#7ecfff;'
        + 'font-size:15px;font-weight:bold;padding:8px 22px;border-radius:8px;'
        + 'border:2px solid #7ecfff;pointer-events:none;z-index:10000000;'
        + 'text-shadow:0 0 8px #7ecfff;letter-spacing:0.5px;';
      hint.textContent = 'Клик 1: верхний-левый угол зоны охоты';
      document.body.appendChild(hint);

      let p1 = null;
      let rectEl = null;

      function drawRect(ax, ay, bx, by) {
        if (!rectEl) {
          rectEl = document.createElement('div');
          rectEl.style.cssText =
            'position:fixed;border:2px dashed #ff4444;'
            + 'background:rgba(255,60,60,0.08);z-index:9999998;pointer-events:none;'
            + 'box-shadow:0 0 0 1px rgba(0,0,0,0.3);';
          document.body.appendChild(rectEl);
        }
        const x = Math.min(ax, bx), y = Math.min(ay, by);
        const w = Math.abs(bx - ax), h = Math.abs(by - ay);
        rectEl.style.left = x + 'px';
        rectEl.style.top  = y + 'px';
        rectEl.style.width  = w + 'px';
        rectEl.style.height = h + 'px';
      }

      function onMove(e) {
        if (p1) drawRect(p1.x, p1.y, e.clientX, e.clientY);
      }

      function onClick(e) {
        e.preventDefault(); e.stopPropagation();
        if (!p1) {
          p1 = { x: e.clientX, y: e.clientY };
          hint.textContent = 'Клик 2: нижний-правый угол зоны охоты';
          // Small dot marker
          const dot = document.createElement('div');
          dot.style.cssText =
            'position:fixed;left:' + (p1.x-5) + 'px;top:' + (p1.y-5) + 'px;'
            + 'width:10px;height:10px;border-radius:50%;'
            + 'background:#ff4444;z-index:10000001;pointer-events:none;'
            + 'box-shadow:0 0 6px red;';
          overlay.appendChild(dot);
        } else {
          const p2 = { x: e.clientX, y: e.clientY };
          cleanup();
          window.__roiPickResult = {
            x1: Math.min(p1.x, p2.x), y1: Math.min(p1.y, p2.y),
            x2: Math.max(p1.x, p2.x), y2: Math.max(p1.y, p2.y)
          };
          window.__roiPickDone = true;
        }
      }

      function cleanup() {
        overlay.removeEventListener('click', onClick);
        overlay.removeEventListener('mousemove', onMove);
        overlay.remove();
        hint.remove();
        if (rectEl) rectEl.remove();
      }

      overlay.addEventListener('click', onClick);
      overlay.addEventListener('mousemove', onMove);
      document.body.appendChild(overlay);
      window.__roiPickDone = false;
      window.__roiPickResult = null;
    })();
  `).catch(e => console.error('roi-pick inject error:', e));

  // Poll until user has clicked twice
  let pollCount = 0;
  const maxPolls = 300; // 60 seconds max
  const pollInterval = setInterval(() => {
    pollCount++;
    if (pollCount > maxPolls) {
      clearInterval(pollInterval);
      // Cancel: remove overlay
      if (gameWindow && !gameWindow.isDestroyed()) {
        gameWindow.webContents.executeJavaScript(
          `document.getElementById('bot-roi-picker')?.remove();` +
          `document.getElementById('bot-roi-hint')?.remove();`
        ).catch(() => {});
      }
      if (controlWindow && !controlWindow.isDestroyed()) {
        controlWindow.webContents.send('roi-pick-cancelled');
      }
      return;
    }

    if (!gameWindow || gameWindow.isDestroyed()) {
      clearInterval(pollInterval);
      return;
    }

    gameWindow.webContents.executeJavaScript('window.__roiPickDone ? JSON.stringify(window.__roiPickResult) : null')
      .then(result => {
        if (!result) return;
        clearInterval(pollInterval);
        let pt;
        try { pt = JSON.parse(result); } catch { return; }

        // pt.x1,y1 = top-left CSS px (logical); pt.x2,y2 = bottom-right CSS px
        // gameWindow content bounds in logical px
        const content = gameWindow.getContentBounds();
        const cw = content.width;
        const ch = content.height;

        // Convert CSS px (relative to page) to margins from content edges (logical px)
        const left   = Math.max(0, Math.round(pt.x1));
        const top    = Math.max(0, Math.round(pt.y1));
        const right  = Math.max(0, Math.round(cw - pt.x2));
        const bottom = Math.max(0, Math.round(ch - pt.y2));

        huntROI = { left, top, right, bottom };
        saveHuntROI();
        console.log(`ROI pick done: L=${left} T=${top} R=${right} B=${bottom} (window ${cw}x${ch})`);

        // Send live update to bot if running
        if (botProcess && botProcess.stdin && !botProcess.stdin.destroyed) {
          const physLeft   = Math.round(left   * captureScale);
          const physTop    = Math.round(top    * captureScale);
          const physRight  = Math.round(right  * captureScale);
          const physBottom = Math.round(bottom * captureScale);
          try {
            botProcess.stdin.write(`CMD_SET_HUNT_ROI ${physLeft},${physTop},${physRight},${physBottom}\n`);
          } catch (e) {
            console.error('roi-pick send to bot error:', e);
          }
        }

        // Draw the resulting ROI box permanently
        const cssX1 = left, cssY1 = top, cssX2 = cw - right, cssY2 = ch - bottom;
        const w = cssX2 - cssX1, h = cssY2 - cssY1;
        if (gameWindow && !gameWindow.isDestroyed()) {
          gameWindow.webContents.executeJavaScript(`
            (function(){
              const old = document.getElementById('bot-hunt-roi');
              if (old) old.remove();
              const el = document.createElement('div');
              el.id = 'bot-hunt-roi';
              el.style.cssText =
                'position:fixed;left:${cssX1}px;top:${cssY1}px;'
                + 'width:${w}px;height:${h}px;'
                + 'border:2px solid rgba(255,60,60,0.85);'
                + 'border-radius:3px;z-index:999990;pointer-events:none;'
                + 'box-shadow:0 0 0 1px rgba(0,0,0,0.4);';
              const lbl = document.createElement('div');
              lbl.textContent = 'HUNT';
              lbl.style.cssText =
                'position:absolute;top:2px;left:4px;color:rgba(255,80,80,0.9);'
                + 'font-size:9px;font-weight:bold;text-shadow:1px 1px 0 black;letter-spacing:1px;';
              el.appendChild(lbl);
              document.body.appendChild(el);
            })();
          `).catch(() => {});
        }

        if (controlWindow && !controlWindow.isDestroyed()) {
          controlWindow.webContents.send('roi-pick-done', huntROI);
        }
      })
      .catch(() => {});
  }, 200);
});

ipcMain.on('set-hunt-roi', (_e, data) => {
  huntROI = {
    left:   Math.max(0, parseInt(data.left)   || 0),
    top:    Math.max(0, parseInt(data.top)    || 0),
    right:  Math.max(0, parseInt(data.right)  || 0),
    bottom: Math.max(0, parseInt(data.bottom) || 0),
  };
  saveHuntROI();
  console.log(`Hunt ROI updated: L=${huntROI.left} T=${huntROI.top} R=${huntROI.right} B=${huntROI.bottom}`);

  // Send live update to running bot if active
  if (botProcess && botProcess.stdin && !botProcess.stdin.destroyed) {
    const physLeft   = Math.round(huntROI.left   * captureScale);
    const physTop    = Math.round(huntROI.top    * captureScale);
    const physRight  = Math.round(huntROI.right  * captureScale);
    const physBottom = Math.round(huntROI.bottom * captureScale);
    try {
      botProcess.stdin.write(`CMD_SET_HUNT_ROI ${physLeft},${physTop},${physRight},${physBottom}\n`);
    } catch (e) {
      console.error('set-hunt-roi send error:', e);
    }
  }
});

function startMarkerProcess(opts) {
  if (markerProcess) return;
  const scriptPath = path.join(__dirname, 'bot.py');
  const args = getCaptureArgs(true);   // --record включён
  markerStopToken = `${Date.now()}-${Math.random().toString(36).slice(2, 10)}`;
  args.push('--stop-token', markerStopToken);
  if (opts && opts.label) args.push('--record-label', opts.label);

  markerProcess = spawn(PYTHON, ['-u', scriptPath, ...args], {
    cwd: __dirname,
    stdio: ['pipe', 'pipe', 'pipe'],
    env: { ...process.env, PYTHONUNBUFFERED: '1' }
  });

  markerProcess.stdout.on('data', (data) => {
    const output = data.toString();
    output.split(/\r?\n/).forEach((line) => {
      const trimmed = line.trim();
      if (!trimmed) return;
      console.log(`Marker: ${trimmed}`);

      if (trimmed.startsWith('SHOW_SQUARE:')) {
        const match = trimmed.match(/^SHOW_SQUARE:(\d+(?:\.\d+)?),(\d+(?:\.\d+)?),(.+)$/);
        if (match) {
          showAttentionSquare(parseInt(match[1], 10), parseInt(match[2], 10), match[3].trim());
        }
      }
      if (trimmed === 'HIDE_SQUARE') hideAttentionSquare();

      // Forward povei sample saved events to control window
      if (trimmed.startsWith('POVEI_SAMPLE_SAVED:')) {
        const n = parseInt(trimmed.split(':')[1]) || 0;
        if (controlWindow && !controlWindow.isDestroyed()) {
          controlWindow.webContents.send('povei-sample-saved', { count: n });
        }
      }
    });
    controlWindow.webContents.send('bot-log', output);
  });

  markerProcess.stderr.on('data', (data) => {
    console.error(`Marker Error: ${data}`);
  });

  markerProcess.on('exit', (code, signal) => {
    console.log(`Marker process exited: code=${code}, signal=${signal}`);
    markerProcess = null;
    if (controlWindow && !controlWindow.isDestroyed()) {
      controlWindow.webContents.send('live-marker-stopped');
    }
  });

  console.log(`Marker started with label=${opts && opts.label}`);
}

ipcMain.on('start-live-marker', (_e, opts) => {
  startMarkerProcess(opts);
});

ipcMain.on('mark-povei', () => {
  startMarkerProcess({ label: 'povei' });
});

ipcMain.on('stop-live-marker', () => {
  if (markerProcess) {
    const procRef = markerProcess;
    markerProcess = null;
    try {
      if (procRef.stdin && !procRef.stdin.destroyed) {
        const cmd = markerStopToken ? `CMD_STOP ${markerStopToken}\n` : 'CMD_STOP\n';
        procRef.stdin.write(cmd, () => {
          try { procRef.stdin.end(); } catch {}
        });
      }
      setTimeout(() => {
        if (procRef && !procRef.killed) procRef.kill('SIGKILL');
      }, 1500);
    } catch (e) {
      console.error(`stop-live-marker error: ${e}`);
      try { procRef.kill('SIGKILL'); } catch {}
    }
  }
});

ipcMain.on('open-template-tool', () => {
  // Запускаем make_templates.py в отдельном окне терминала
  const scriptPath = path.join(__dirname, 'make_templates.py');
  const proc = spawn(PYTHON, [scriptPath], {
    cwd: __dirname,
    detached: true,
    stdio: 'inherit'   // окно консоли видно пользователю
  });
  proc.unref();
  console.log('Template tool launched');
});

ipcMain.on('scan-povei', () => {
  // Если бот запущен — сканируем через него (он видит SHOW_SQUARE)
  if (botProcess && botProcess.stdin && !botProcess.stdin.destroyed) {
    try {
      botProcess.stdin.write('CMD_SCAN_POVEI\n');
      console.log('Scan povei: sent CMD_SCAN_POVEI to running bot');
    } catch (e) {
      console.error('scan-povei via bot error:', e);
    }
    return;
  }

  // Бот не запущен — отдельный процесс
  const scriptPath = path.join(__dirname, 'bot.py');
  const args = getCaptureArgs(false);
  args.push('--scan-povei');

  const proc = spawn(PYTHON, ['-u', scriptPath, ...args], {
    cwd: __dirname,
    stdio: ['pipe', 'pipe', 'pipe'],
    env: { ...process.env, PYTHONUNBUFFERED: '1' }
  });

  let output = '';
  proc.stdout.on('data', (d) => {
    const chunk = d.toString();
    output += chunk;
    controlWindow.webContents.send('bot-log', chunk);
    // Перехватываем SHOW_SQUARE из отдельного процесса
    chunk.split(/\r?\n/).forEach(line => {
      const trimmed = line.trim();
      if (trimmed.startsWith('SHOW_SQUARE:')) {
        const m = trimmed.match(/^SHOW_SQUARE:(\d+),(\d+),(.+)$/);
        if (m) showAttentionSquare(parseInt(m[1], 10), parseInt(m[2], 10), m[3].trim());
      }
    });
  });
  proc.stderr.on('data', (d) => console.error(`scan-povei stderr: ${d}`));
  proc.on('exit', () => {
    const match = output.match(/SCAN_POVEI_RESULT:({.+})/);
    if (match) {
      try {
        const data = JSON.parse(match[1]);
        if (controlWindow && !controlWindow.isDestroyed()) {
          controlWindow.webContents.send('scan-povei-result', data);
        }
      } catch (e) {
        console.error('scan-povei parse error:', e);
      }
    }
  });
  console.log('Scan povei launched (standalone)');
});

ipcMain.on('start-bot', () => {
  if (!botProcess) {
    const scriptPath = path.join(__dirname, 'bot.py');
    const args = getCaptureArgs(false);
    botStopToken = `${Date.now()}-${Math.random().toString(36).slice(2, 10)}`;
    args.push('--stop-token', botStopToken);

    botProcess = spawn(PYTHON, ['-u', scriptPath, ...args], {
      cwd: __dirname,
      stdio: ['pipe', 'pipe', 'pipe'],
      env: { ...process.env, PYTHONUNBUFFERED: '1' }
    });

    wireBotProcess(botProcess, 'Bot');

    controlWindow.webContents.send('bot-status', { running: true });
  }
});

ipcMain.on('start-bot-record', (_e, opts) => {
  if (!botProcess) {
    const scriptPath = path.join(__dirname, 'bot.py');
    const args = getCaptureArgs(true);
    botStopToken = `${Date.now()}-${Math.random().toString(36).slice(2, 10)}`;
    args.push('--stop-token', botStopToken);
    if (opts && opts.label) args.push('--record-label', opts.label);

    botProcess = spawn(PYTHON, ['-u', scriptPath, ...args], {
      cwd: __dirname,
      stdio: ['pipe', 'pipe', 'pipe'],
      env: { ...process.env, PYTHONUNBUFFERED: '1' }
    });

    wireBotProcess(botProcess, 'Record');

    controlWindow.webContents.send('bot-status', { running: true });
  }
});

ipcMain.on('stop-bot', () => {
  if (botProcess) {
    const procRef = botProcess;
    botProcess = null;
    try {
      // Пишем CMD_STOP и сразу закрываем stdin — Python получит EOF и выйдет из for-loop
      if (procRef.stdin && !procRef.stdin.destroyed) {
        const cmd = botStopToken ? `CMD_STOP ${botStopToken}\n` : 'CMD_STOP\n';
        procRef.stdin.write(cmd, () => {
          try { procRef.stdin.end(); } catch {}
        });
      }
      // Принудительно убиваем через 1.5 сек если не вышел сам
      setTimeout(() => {
        if (procRef && !procRef.killed) {
          console.log('Force killing bot process...');
          procRef.kill('SIGKILL');
        }
      }, 1500);
    } catch (e) {
      console.error(`stop-bot error: ${e}`);
      try { procRef.kill('SIGKILL'); } catch {}
    }
  }
});

// Отображение маркеров кандидатов в браузере
// При каждом вызове стираем только маркеры тех labels, которые пришли в items,
// затем рисуем новые — так povei-маркеры остаются на месте пока не придут новые povei.
// При HIDE_CANDIDATES — стираем все.
function showCandidateMarkers(items) {
  if (!gameWindow || gameWindow.isDestroyed()) return;

  const CANDIDATE_TTL = 50000; // 50 сек — маркеры живут всё время добычи (max ~39s), статичные

  // Color per label
  const colorMap = {
    vkusn:      '#ff44ff',   // bright magenta — vkusnocvet
    vkusnocvet: '#ff44ff',
    povei:      '#44ff88',   // green — povei
    recorded:   '#ffcc00',   // yellow
  };
  const defaultColor = '#00cfff';

  // Собираем уникальные labels из текущего набора
  const labelsInBatch = [...new Set(items.map(i => i.label))];

  const markerJS = items.map((item, i) => {
    const cssX  = Math.round(item.x / captureScale);
    const cssY  = Math.round(item.y / captureScale);
    const color = colorMap[item.label] || defaultColor;
    const pct   = Math.round((item.conf || 0) * 100);
    const id    = `bot-cand-${item.label}-${i}`;
    return `
      (function(){
        const old = document.getElementById(${JSON.stringify(id)});
        if (old) old.remove();
        const el = document.createElement('div');
        el.id = ${JSON.stringify(id)};
        el.className = 'bot-candidate';
        el.dataset.label = ${JSON.stringify(item.label)};
        el.style.cssText =
          'position:fixed;left:' + (${cssX}-28) + 'px;top:' + (${cssY}-28) + 'px;'
          + 'width:56px;height:56px;'
          + 'border:3px solid ' + ${JSON.stringify(color)} + ';'
          + 'border-radius:50%;z-index:999998;pointer-events:none;'
          + 'box-shadow:0 0 12px 3px ' + ${JSON.stringify(color)} + ','
          + 'inset 0 0 8px rgba(0,0,0,0.4);'
          + 'background:rgba(0,0,0,0.15);'
          + 'animation:bot-cand-pulse 0.9s ease-in-out infinite alternate;';
        const lbl = document.createElement('div');
        lbl.textContent = ${JSON.stringify(item.label)} + ' ' + ${pct} + '%';
        lbl.style.cssText =
          'position:absolute;top:-22px;left:50%;transform:translateX(-50%);'
          + 'color:#fff;font-size:11px;font-weight:bold;'
          + 'text-shadow:0 0 4px ' + ${JSON.stringify(color)} + ',1px 1px 0 black;'
          + 'white-space:nowrap;background:rgba(0,0,0,0.55);'
          + 'padding:1px 5px;border-radius:4px;';
        el.appendChild(lbl);
        document.body.appendChild(el);
        if (!document.getElementById('bot-cand-style')) {
          const st = document.createElement('style');
          st.id = 'bot-cand-style';
          st.textContent = '@keyframes bot-cand-pulse{from{opacity:1}to{opacity:0.45}}';
          document.head.appendChild(st);
        }
        setTimeout(() => el.remove(), ${CANDIDATE_TTL});
      })();
    `;
  }).join('\n');

  // Стираем только маркеры тех labels, которые пришли в этом батче
  // (чтобы повей-маркеры не пропадали при обновлении только vkusn и наоборот)
  const clearByLabelJS = labelsInBatch.map(lbl =>
    `document.querySelectorAll('.bot-candidate[data-label=${JSON.stringify(lbl)}]').forEach(e=>e.remove());`
  ).join('');

  gameWindow.webContents.executeJavaScript(clearByLabelJS + markerJS).catch(() => {});
}

// Постоянная синяя рамка зоны чата
function showChatROI(ax1, ay1, ax2, ay2) {
  if (!gameWindow || gameWindow.isDestroyed()) return;
  const cssX1 = Math.round(ax1 / captureScale);
  const cssY1 = Math.round(ay1 / captureScale);
  const cssX2 = Math.round(ax2 / captureScale);
  const cssY2 = Math.round(ay2 / captureScale);
  const w = cssX2 - cssX1, h = cssY2 - cssY1;
  gameWindow.webContents.executeJavaScript(`
    (function(){
      const old = document.getElementById('bot-chat-roi');
      if (old) old.remove();
      const el = document.createElement('div');
      el.id = 'bot-chat-roi';
      el.style.cssText =
        'position:fixed;left:${cssX1}px;top:${cssY1}px;'
        + 'width:${w}px;height:${h}px;'
        + 'border:2px solid rgba(60,180,255,0.85);'
        + 'border-radius:3px;z-index:999991;pointer-events:none;'
        + 'box-shadow:0 0 0 1px rgba(0,0,0,0.4);';
      const lbl = document.createElement('div');
      lbl.textContent = 'CHAT';
      lbl.style.cssText =
        'position:absolute;top:2px;left:4px;color:rgba(60,180,255,0.9);'
        + 'font-size:9px;font-weight:bold;text-shadow:1px 1px 0 black;letter-spacing:1px;';
      el.appendChild(lbl);
      document.body.appendChild(el);
      setTimeout(() => el.remove(), 4000);
    })();
  `).catch(() => {});
}

// ── Chat ROI config IPC ──────────────────────────────────────────────────────
ipcMain.handle('get-chat-roi', () => chatROI);

ipcMain.on('set-chat-roi', (_e, data) => {
  chatROI = {
    left:   Math.max(0, parseInt(data.left)   || 0),
    top:    Math.max(0, parseInt(data.top)    || 0),
    right:  Math.max(0, parseInt(data.right)  || 0),
    bottom: Math.max(0, parseInt(data.bottom) || 0),
  };
  saveChatROI();
  console.log(`Chat ROI updated: L=${chatROI.left} T=${chatROI.top} R=${chatROI.right} B=${chatROI.bottom}`);
  if (botProcess && botProcess.stdin && !botProcess.stdin.destroyed) {
    const physLeft   = Math.round(chatROI.left   * captureScale);
    const physTop    = Math.round(chatROI.top    * captureScale);
    const physRight  = Math.round(chatROI.right  * captureScale);
    const physBottom = Math.round(chatROI.bottom * captureScale);
    try {
      botProcess.stdin.write(`CMD_SET_CHAT_ROI ${physLeft},${physTop},${physRight},${physBottom}\n`);
    } catch (e) {
      console.error('set-chat-roi send error:', e);
    }
  }
});

// ── Chat ROI two-point picker ────────────────────────────────────────────────
ipcMain.on('start-chat-roi-pick', () => {
  if (!gameWindow || gameWindow.isDestroyed()) return;
  console.log('Chat ROI pick started');
  if (controlWindow && !controlWindow.isDestroyed()) {
    controlWindow.webContents.send('chat-roi-pick-started');
  }

  gameWindow.webContents.executeJavaScript(`
    (function() {
      const oldOverlay = document.getElementById('bot-chat-roi-picker');
      if (oldOverlay) oldOverlay.remove();
      const overlay = document.createElement('div');
      overlay.id = 'bot-chat-roi-picker';
      overlay.style.cssText = 'position:fixed;left:0;top:0;right:0;bottom:0;z-index:9999999;cursor:crosshair;background:rgba(0,80,40,0.18);';
      const hint = document.createElement('div');
      hint.id = 'bot-chat-roi-hint';
      hint.style.cssText = 'position:fixed;top:14px;left:50%;transform:translateX(-50%);background:rgba(0,0,0,0.82);color:#7ecfff;font-size:15px;font-weight:bold;padding:8px 22px;border-radius:8px;border:2px solid #3cb4ff;pointer-events:none;z-index:10000000;text-shadow:0 0 8px #3cb4ff;';
      hint.textContent = 'ЧАТ — Клик 1: верхний-левый угол зоны чата';
      document.body.appendChild(hint);
      let p1 = null, rectEl = null;
      function drawRect(ax,ay,bx,by){
        if(!rectEl){rectEl=document.createElement('div');rectEl.style.cssText='position:fixed;border:2px dashed #3cb4ff;background:rgba(60,180,255,0.08);z-index:9999998;pointer-events:none;';document.body.appendChild(rectEl);}
        const x=Math.min(ax,bx),y=Math.min(ay,by);
        rectEl.style.left=x+'px';rectEl.style.top=y+'px';rectEl.style.width=Math.abs(bx-ax)+'px';rectEl.style.height=Math.abs(by-ay)+'px';
      }
      function onMove(e){if(p1)drawRect(p1.x,p1.y,e.clientX,e.clientY);}
      function onClick(e){
        e.preventDefault();e.stopPropagation();
        if(!p1){
          p1={x:e.clientX,y:e.clientY};
          hint.textContent='ЧАТ — Клик 2: нижний-правый угол зоны чата';
          const dot=document.createElement('div');dot.style.cssText='position:fixed;left:'+(p1.x-5)+'px;top:'+(p1.y-5)+'px;width:10px;height:10px;border-radius:50%;background:#3cb4ff;z-index:10000001;pointer-events:none;';overlay.appendChild(dot);
        } else {
          const p2={x:e.clientX,y:e.clientY};
          cleanup();
          window.__chatRoiPickResult={x1:Math.min(p1.x,p2.x),y1:Math.min(p1.y,p2.y),x2:Math.max(p1.x,p2.x),y2:Math.max(p1.y,p2.y)};
          window.__chatRoiPickDone=true;
        }
      }
      function cleanup(){overlay.removeEventListener('click',onClick);overlay.removeEventListener('mousemove',onMove);overlay.remove();hint.remove();if(rectEl)rectEl.remove();}
      overlay.addEventListener('click',onClick);overlay.addEventListener('mousemove',onMove);
      document.body.appendChild(overlay);
      window.__chatRoiPickDone=false;window.__chatRoiPickResult=null;
    })();
  `).catch(e => console.error('chat-roi-pick inject error:', e));

  let pollCount = 0;
  const pollInterval = setInterval(() => {
    if (++pollCount > 300) {
      clearInterval(pollInterval);
      if (gameWindow && !gameWindow.isDestroyed()) {
        gameWindow.webContents.executeJavaScript(`document.getElementById('bot-chat-roi-picker')?.remove();document.getElementById('bot-chat-roi-hint')?.remove();`).catch(()=>{});
      }
      if (controlWindow && !controlWindow.isDestroyed()) controlWindow.webContents.send('chat-roi-pick-cancelled');
      return;
    }
    if (!gameWindow || gameWindow.isDestroyed()) { clearInterval(pollInterval); return; }
    gameWindow.webContents.executeJavaScript('window.__chatRoiPickDone ? JSON.stringify(window.__chatRoiPickResult) : null')
      .then(result => {
        if (!result) return;
        clearInterval(pollInterval);
        let pt; try { pt = JSON.parse(result); } catch { return; }
        const content = gameWindow.getContentBounds();
        const left   = Math.max(0, Math.round(pt.x1 * captureScale));
        const top    = Math.max(0, Math.round(pt.y1 * captureScale));
        const right  = Math.max(0, Math.round((content.width  - pt.x2) * captureScale));
        const bottom = Math.max(0, Math.round((content.height - pt.y2) * captureScale));
        chatROI = { left, top, right, bottom };
        saveChatROI();
        console.log(`Chat ROI pick done: L=${left} T=${top} R=${right} B=${bottom}`);
        if (botProcess && botProcess.stdin && !botProcess.stdin.destroyed) {
          try { botProcess.stdin.write(`CMD_SET_CHAT_ROI ${left},${top},${right},${bottom}\n`); } catch(e){}
        }
        // Draw blue outline
        const cssX1=Math.round(pt.x1), cssY1=Math.round(pt.y1);
        const w=Math.round(pt.x2-pt.x1), h=Math.round(pt.y2-pt.y1);
        if (gameWindow && !gameWindow.isDestroyed()) {
          gameWindow.webContents.executeJavaScript(`
            (function(){
              const old=document.getElementById('bot-chat-roi');if(old)old.remove();
              const el=document.createElement('div');el.id='bot-chat-roi';
              el.style.cssText='position:fixed;left:${cssX1}px;top:${cssY1}px;width:${w}px;height:${h}px;border:2px solid rgba(60,180,255,0.85);border-radius:3px;z-index:999991;pointer-events:none;';
              const lbl=document.createElement('div');lbl.textContent='CHAT';lbl.style.cssText='position:absolute;top:2px;left:4px;color:rgba(60,180,255,0.9);font-size:9px;font-weight:bold;text-shadow:1px 1px 0 black;letter-spacing:1px;';
              el.appendChild(lbl);document.body.appendChild(el);
            })();
          `).catch(()=>{});
        }
        if (controlWindow && !controlWindow.isDestroyed()) controlWindow.webContents.send('chat-roi-pick-done', chatROI);
      }).catch(()=>{});
  }, 200);
});

ipcMain.on('save-chat-tpl', (_e, label) => {
  if (botProcess && botProcess.stdin && !botProcess.stdin.destroyed) {
    try { botProcess.stdin.write(`CMD_SAVE_CHAT_TPL ${label || 'unknown'}\n`); } catch(e){}
  }
});

// Постоянная красная рамка зоны охоты
function showHuntROI(ax1, ay1, ax2, ay2) {
  if (!gameWindow || gameWindow.isDestroyed()) return;
  const cssX1 = Math.round(ax1 / captureScale);
  const cssY1 = Math.round(ay1 / captureScale);
  const cssX2 = Math.round(ax2 / captureScale);
  const cssY2 = Math.round(ay2 / captureScale);
  const w = cssX2 - cssX1;
  const h = cssY2 - cssY1;
  gameWindow.webContents.executeJavaScript(`
    (function(){
      const old = document.getElementById('bot-hunt-roi');
      if (old) old.remove();
      const el = document.createElement('div');
      el.id = 'bot-hunt-roi';
      el.style.cssText =
        'position:fixed;left:${cssX1}px;top:${cssY1}px;'
        + 'width:${w}px;height:${h}px;'
        + 'border:2px solid rgba(255,60,60,0.75);'
        + 'border-radius:3px;z-index:999990;pointer-events:none;'
        + 'box-shadow:0 0 0 1px rgba(0,0,0,0.4);';
      const lbl = document.createElement('div');
      lbl.textContent = 'HUNT';
      lbl.style.cssText =
        'position:absolute;top:2px;left:4px;color:rgba(255,80,80,0.85);'
        + 'font-size:9px;font-weight:bold;text-shadow:1px 1px 0 black;'
        + 'letter-spacing:1px;';
      el.appendChild(lbl);
      document.body.appendChild(el);
    })();
  `).catch(() => {});
}

function showAttentionSquare(x, y, name) {
  if (gameWindow && !gameWindow.isDestroyed()) {
    // x/y приходят в физических пикселях; DOM работает в CSS px
    const cssX = Math.round(x / captureScale);
    const cssY = Math.round(y / captureScale);

    const isCursor = name === 'Cursor';
    // Цвет и стиль зависит от типа ресурса
    const nameLower = name.toLowerCase();
    const isScan = nameLower.startsWith('povei_scan_') || nameLower.startsWith('vkusn_scan_');
    const isGathering = nameLower === 'gathering';
    const ttlMs = (isCursor || isScan) ? 300 : isGathering ? 60000 : 4000;
    let color, glowColor, displayName;

    if (isGathering) {
      // Actively gathering — bright red pulsing ring, NO background, NO crosshair
      color = '#ff2222'; glowColor = '#ff0000';
      displayName = '⛏ добыча';
    } else if (nameLower.startsWith('povei_scan_')) {
      const pct = nameLower.split('_').pop();
      color = '#44ff88'; glowColor = '#44ff88';
      displayName = `повей ~${pct}%`;
    } else if (nameLower.startsWith('vkusn_scan_')) {
      const pct = nameLower.split('_').pop();
      color = '#ff44ff'; glowColor = '#ff44ff';
      displayName = `вкусн ~${pct}%`;
    } else if (nameLower.startsWith('povei_')) {
      const pct = nameLower.split('_').pop();
      color = '#44ff88'; glowColor = '#44ff88';
      displayName = `повей ${pct}%`;
    } else if (nameLower.startsWith('vkusnocvet_') || nameLower.startsWith('vkusn_')) {
      const pct = nameLower.split('_').pop();
      color = '#ff44ff'; glowColor = '#ff44ff';
      displayName = `вкусн ${pct}%`;
    } else if (nameLower.includes('povei')) {
      color = '#44ff88'; glowColor = '#44ff88';
      displayName = name;
    } else if (nameLower.includes('weak')) {
      color = '#ffd740'; glowColor = '#ffd740';
      displayName = name;
    } else if (nameLower.includes('match') || nameLower.includes('vkusn')) {
      color = '#ff44ff'; glowColor = '#ff44ff';
      displayName = name;
    } else if (isCursor) {
      color = '#00cfff'; glowColor = '#00cfff';
      displayName = '';
    } else {
      color = '#ff4444'; glowColor = 'red';
      displayName = name;
    }

    // Радиус кольца: для добычи чуть больше, иначе стандартный
    const ringR = isGathering ? 36 : 28;

    gameWindow.webContents.executeJavaScript(`
      (function() {
        const old = document.getElementById('bot-attention-square');
        if (old) old.remove();

        // Inject pulse animation style if not already present
        if (!document.getElementById('bot-gathering-style')) {
          const st = document.createElement('style');
          st.id = 'bot-gathering-style';
          st.textContent = \`
            @keyframes bot-ring-pulse {
              0%,100%{ box-shadow:0 0 14px 4px ${glowColor}, 0 0 0 2px ${color}; opacity:0.95; }
              50%{ box-shadow:0 0 28px 10px ${glowColor}, 0 0 0 2px ${color}; opacity:1; }
            }
            @keyframes bot-ring-still {
              0%,100%{ box-shadow:0 0 10px 3px ${glowColor}, 0 0 0 2px ${color}; }
            }
          \`;
          document.head.appendChild(st);
        }

        const R = ${ringR};
        const ring = document.createElement('div');
        ring.id = 'bot-attention-square';
        const anim = ${isGathering}
          ? 'animation:bot-ring-pulse 0.7s ease-in-out infinite;'
          : 'animation:bot-ring-still 2s ease-in-out infinite;';
        // Кольцо: прозрачный фон, только граница + glow. Без крестика.
        ring.style.cssText =
          'position:fixed;'
          + 'left:' + (${cssX} - R) + 'px;top:' + (${cssY} - R) + 'px;'
          + 'width:' + (R*2) + 'px;height:' + (R*2) + 'px;'
          + 'border:3px solid ${color};'
          + 'border-radius:50%;'
          + 'background:transparent;'
          + 'z-index:999999;pointer-events:none;'
          + 'box-shadow:0 0 14px 4px ${glowColor};'
          + anim;

        const label = document.createElement('div');
        label.textContent = ${JSON.stringify(displayName)};
        label.style.cssText =
          'position:absolute;top:-22px;left:50%;transform:translateX(-50%);'
          + 'color:${color};font-weight:bold;font-size:12px;'
          + 'text-shadow:1px 1px 2px black;white-space:nowrap;'
          + 'background:rgba(0,0,0,0.5);padding:1px 5px;border-radius:3px;'
          + (${JSON.stringify(displayName)} ? '' : 'display:none');
        ring.appendChild(label);

        document.body.appendChild(ring);
        setTimeout(() => { if (ring.parentNode) ring.remove(); }, ${ttlMs});
      })();
    `);
  }
}

// Текущая метка для Ctrl+M hint — обновляется из control.html
let hintLabel = 'povei';
ipcMain.on('set-hint-label', (_e, label) => {
  if (['povei', 'vkusnocvet'].includes(label)) {
    hintLabel = label;
    console.log(`Hint label set to: ${hintLabel}`);
  }
});

app.whenReady().then(() => {
  createWindows();

  // F8 — аварийная остановка бота из любого места
  globalShortcut.register('F8', () => {
    console.log('F8 pressed — emergency stop');
    if (botProcess) {
      const procRef = botProcess;
      botProcess = null;
      try { procRef.stdin && procRef.stdin.end(); } catch {}
      try { procRef.kill('SIGKILL'); } catch {}
    }
    if (markerProcess) {
      const procRef = markerProcess;
      markerProcess = null;
      try { procRef.stdin && procRef.stdin.end(); } catch {}
      try { procRef.kill('SIGKILL'); } catch {}
    }
    if (gameWindow && !gameWindow.isDestroyed()) {
      gameWindow.webContents.executeJavaScript(
        `document.getElementById('bot-hunt-roi')?.remove();` +
        `document.querySelectorAll('.bot-candidate').forEach(e=>e.remove());`
      ).catch(() => {});
    }
    if (controlWindow && !controlWindow.isDestroyed()) {
      controlWindow.webContents.send('bot-status', { running: false });
      controlWindow.webContents.send('live-marker-stopped');
      controlWindow.webContents.send('bot-log', 'F8: Bot force stopped\n');
    }
  });

  // Ctrl+M — подсказка модели на ходу: указать где ресурс (работает во время добычи)
  globalShortcut.register('CommandOrControl+M', () => {
    if (!botProcess || !botProcess.stdin || botProcess.stdin.destroyed) {
      console.log('Ctrl+M: bot not running, ignoring');
      if (controlWindow && !controlWindow.isDestroyed()) {
        controlWindow.webContents.send('bot-log', '⚠️ Ctrl+M: бот не запущен\n');
      }
      return;
    }

    const cursorPos = screen.getCursorScreenPoint();
    const content   = gameWindow.getContentBounds();

    if (cursorPos.x < content.x || cursorPos.x > content.x + content.width ||
        cursorPos.y < content.y || cursorPos.y > content.y + content.height) {
      console.log('Ctrl+M: cursor outside game window');
      if (controlWindow && !controlWindow.isDestroyed()) {
        controlWindow.webContents.send('bot-log', '⚠️ Ctrl+M: курсор вне игрового окна\n');
      }
      return;
    }

    const lx = cursorPos.x - content.x;
    const ly = cursorPos.y - content.y;
    const px = Math.round(lx * captureScale);
    const py = Math.round(ly * captureScale);
    const label = hintLabel;

    console.log(`Ctrl+M: hint ${label} at cursor logical=(${lx},${ly}) phys=(${px},${py})`);
    try {
      botProcess.stdin.write(`CMD_HINT ${label} ${px},${py}\n`);
    } catch (e) {
      console.error('Ctrl+M write error:', e);
    }
    if (controlWindow && !controlWindow.isDestroyed()) {
      const icon = label === 'povei' ? '🌿' : '🌸';
      controlWindow.webContents.send('bot-log', `${icon} Ctrl+M: подсказка [${label}] → (${lx},${ly})\n`);
    }
  });
});

app.on('will-quit', () => {
  globalShortcut.unregisterAll();
});

app.on('window-all-closed', () => {
  if (botProcess) botProcess.kill();
  if (markerProcess) markerProcess.kill();
  app.quit();
});


