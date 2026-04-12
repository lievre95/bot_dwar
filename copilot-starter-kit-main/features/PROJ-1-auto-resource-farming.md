# PROJ-1: Автодобыча ресурсов (Auto Resource Farming)

**Status:** 🔵 Planned  
**Created:** 2026-04-11  
**Last Updated:** 2026-04-11  
**Priority:** P0 (MVP)

---

## User Stories

### US-1: Автоматический крафт ресурсов
**Как** игрок Dwar  
**Я хочу** автоматически кликать на объекты для сбора ресурсов  
**Чтобы** фармить материалы без ручного труда

### US-2: Определение типа ресурса
**Как** пользователь бота  
**Я хочу** выбрать тип ресурса для фарма (трава, руда, дерево и т.д.)  
**Чтобы** собирать именно те материалы, которые мне нужны

### US-3: Мониторинг статуса сбора
**Как** пользователь бота  
**Я хочу** видеть в реальном времени: сколько ресурсов собрано, время работы, скорость фарма  
**Чтобы** оценить эффективность бота

---

## Acceptance Criteria

### AC-1: Обнаружение игровых элементов
- [ ] Бот находит игровое окно Dwar в браузере (или по URL dwar.ru)
- [ ] Бот определяет координаты кнопок/объектов для клика (трава, руда и т.д.)
- [ ] Бот распознаёт текущую локацию персонажа по DOM

### AC-2: Цикл крафта
- [ ] Бот кликает на выбранный ресурс с интервалом 1-3 секунды
- [ ] Бот ждёт завершения анимации сбора (прогресс-бар)
- [ ] Бот автоматически начинает новый цикл после завершения

### AC-3: Обработка ошибок
- [ ] Если ресурс закончился (объект исчез), бот переключается на соседний
- [ ] Если инвентарь заполнен, бот останавливается и оповещает пользователя
- [ ] Если персонаж получил урон, бот приоритизирует автобой (PROJ-2)

### AC-4: UI панель управления
- [ ] Кнопка **Start/Stop** для запуска/остановки бота
- [ ] Dropdown выбора типа ресурса (трава, руда, дерево)
- [ ] Счетчик собранных ресурсов в реальном времени
- [ ] Таймер работы (hh:mm:ss)
- [ ] Индикатор скорости (ресурсов/час)

### AC-5: Логирование
- [ ] Все действия бота записываются в журнал с timestamp
- [ ] Пользователь может скачать лог в `.txt` формате
- [ ] Лог включает: время старта/стопа, тип ресурса, количество собранных, ошибки

---

## Edge Cases

### EC-1: Лаг или медленная загрузка страницы
- **Проблема**: DOM элементы загружаются с задержкой, бот кликает в пустоту
- **Решение**: Retry-механизм (3 попытки с ожиданием 2 секунды), затем ошибка

### EC-2: Изменение структуры DOM игры (обновление dwar.ru)
- **Проблема**: Селекторы элементов устарели, бот не находит кнопки
- **Решение**: Конфигурационный файл с селекторами (легко обновить вручную)

### EC-3: Окно игры неактивно (свёрнуто или в фоне)
- **Проблема**: Браузер может ограничить выполнение JS в неактивной вкладке
- **Решение**: Предупреждение пользователю "Держите вкладку активной"

### EC-4: Одновременная атака монстра во время крафта
- **Проблема**: Персонаж получает урон, бот продолжает фармить
- **Решение**: Прерывание цикла крафта, переключение в режим автобоя (PROJ-2)

### EC-5: Капча во время работы
- **Проблема**: Игра показала капчу, бот заблокирован
- **Решение**: Детектор капчи (PROJ-4) останавливает все действия и воспроизводит звук

---

## Tech Design

### Architecture Overview
```
DwarBot (Electron/Web Extension)
├── Core Engine
│   ├── DOMScanner (находит элементы игры)
│   ├── ActionExecutor (кликает, ждёт анимацию)
│   └── StateManager (текущая локация, здоровье, инвентарь)
├── Farming Module
│   ├── ResourceSelector (выбор типа ресурса)
│   ├── FarmingLoop (цикл клик → ожидание → клик)
│   └── ResourceCounter (подсчёт собранных)
└── UI Dashboard (Next.js)
    ├── ControlPanel (Start/Stop, настройки)
    ├── StatsDisplay (счётчики, графики)
    └── LogViewer (журнал действий)
```

### Technology Stack
- **Automation**: Puppeteer (headless Chrome) или Playwright для управления браузером
- **UI**: Next.js + Tailwind + shadcn/ui (уже есть в проекте)
- **State**: Zustand или React Context (легковесный стейт-менеджмент)
- **Logging**: Winston (структурированные логи в файл)
- **Config**: JSON файл с селекторами DOM элементов игры

### Database Schema (Optional, Supabase)
```sql
-- Таблица для хранения статистики фарма
CREATE TABLE farming_sessions (
  id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
  user_id UUID REFERENCES auth.users(id),
  started_at TIMESTAMP DEFAULT NOW(),
  ended_at TIMESTAMP,
  resource_type TEXT NOT NULL, -- 'herb', 'ore', 'wood'
  resources_collected INTEGER DEFAULT 0,
  duration_seconds INTEGER,
  errors_count INTEGER DEFAULT 0,
  created_at TIMESTAMP DEFAULT NOW()
);

-- Индекс для быстрого поиска сессий пользователя
CREATE INDEX idx_farming_sessions_user_id ON farming_sessions(user_id);
```

### Component Tree (UI)
```
DwarBotDashboard (src/app/page.tsx)
├── BotControlPanel
│   ├── StartStopButton
│   ├── ResourceTypeSelect (dropdown: herb/ore/wood)
│   └── StatusBadge (active/paused/error)
├── StatsPanel
│   ├── ResourceCounter (live count)
│   ├── FarmingTimer (HH:MM:SS)
│   └── EfficiencyChart (resources/hour)
└── ActivityLog
    ├── LogEntry[] (timestamp + action + result)
    └── DownloadLogButton
```

### API Routes (if needed)
- `POST /api/bot/start` — запустить бота
- `POST /api/bot/stop` — остановить бота
- `GET /api/bot/status` — текущий статус (running/paused/error)
- `GET /api/bot/stats` — статистика текущей сессии
- `GET /api/bot/logs` — последние 100 записей лога

---

## Dependencies
- `puppeteer` или `playwright` для автоматизации браузера
- `winston` для логирования
- `zustand` для state management (опционально)

---

## Implementation Notes

### Шаг 1: Исследование DOM структуры Dwar
- [ ] Открыть dwar.ru в DevTools
- [ ] Найти селекторы для кнопок крафта (трава, руда и т.д.)
- [ ] Найти элемент прогресс-бара сбора ресурсов
- [ ] Найти индикатор заполнения инвентаря
- [ ] Сохранить все селекторы в `config/dwar-selectors.json`

### Шаг 2: Создать базовый Puppeteer-скрипт
```typescript
// Пример: автоматический клик на траву
const browser = await puppeteer.launch({ headless: false });
const page = await browser.newPage();
await page.goto('https://dwar.ru');

// Логин (если нужен)
await page.type('#username', process.env.DWAR_USERNAME);
await page.type('#password', process.env.DWAR_PASSWORD);
await page.click('#login-button');

// Цикл крафта
while (true) {
  await page.click('.herb-gather-button'); // селектор из config
  await page.waitForSelector('.progress-complete', { timeout: 5000 });
  console.log('Ресурс собран!');
}
```

### Шаг 3: Обернуть логику в React UI
- [ ] Создать `src/components/DwarBot/BotController.tsx`
- [ ] Добавить кнопки Start/Stop, которые вызывают API `/api/bot/start`
- [ ] API запускает Puppeteer-скрипт в background процессе

### Шаг 4: Real-time обновление UI
- [ ] WebSocket или Server-Sent Events для трансляции статуса бота
- [ ] UI обновляет счётчик ресурсов каждую секунду

---

## Testing Checklist

### Manual Testing
- [ ] Бот успешно логинится в игру
- [ ] Бот кликает на ресурс и ждёт завершения сбора
- [ ] Счётчик ресурсов увеличивается после каждого сбора
- [ ] Бот останавливается при нажатии Stop
- [ ] Лог записывает все действия с timestamp

### Automated Testing (Playwright)
- [ ] E2E тест: запуск бота → сбор 5 ресурсов → остановка
- [ ] Unit тест: `DOMScanner` находит элементы по селектору
- [ ] Unit тест: `ResourceCounter` корректно увеличивает счётчик

---

## Security Considerations
- ⚠️ **Не хранить пароли в коде**: использовать `.env.local` для DWAR_USERNAME/PASSWORD
- ⚠️ **Риск бана**: dwar.ru может детектировать автоматизацию, использовать на свой риск
- ⚠️ **CAPTCHA**: бот не может обойти капчу автоматически (PROJ-4 для оповещения)

---

## Future Enhancements (Post-MVP)
- 🔮 Мультиаккаунт: управление 2+ персонажами одновременно
- 🔮 Машинное обучение: оптимизация маршрута сбора ресурсов
- 🔮 Telegram Bot: управление и оповещения через Telegram
- 🔮 Облачное развёртывание: запуск бота на VPS 24/7

---

## Deployment

_Will be filled by DevOps Engineer after deployment_

**Status:** ⏳ Not Yet Deployed  
**Production URL:** TBD  
**Git Tag:** TBD

