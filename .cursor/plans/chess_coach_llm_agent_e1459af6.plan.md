---
name: Chess Coach LLM Agent
overview: "Разработка LLM-агента шахматного коуча: FastAPI бэкенд с Stockfish-анализом и LiteLLM для текстовых комментариев, React фронтенд с интерактивной доской, PostgreSQL для хранения партий и аналитики."
todos:
  - id: phase-1-foundation
    content: "Phase 1: Init project (pyproject.toml, Docker Compose, DB models, Alembic, FastAPI skeleton)"
    status: completed
  - id: phase-2-core-engine
    content: "Phase 2: PGN parser + Stockfish analyzer services + Celery tasks"
    status: completed
  - id: phase-3-llm-coach
    content: "Phase 3: LiteLLM integration, prompt templates, per-move/game/period commentary"
    status: completed
  - id: phase-4-api
    content: "Phase 4: REST API endpoints (upload, analysis, reports)"
    status: completed
  - id: phase-5-frontend
    content: "Phase 5: React app (chessboard, move list, commentary panel, upload)"
    status: completed
  - id: phase-6-reports
    content: "Phase 6: Period reports -- aggregation + LLM recommendations"
    status: completed
  - id: phase-7-polish
    content: "Phase 7: Tests, error handling, Stockfish optimization, LLM streaming"
    status: completed
  - id: todo-1771171075698-rpg1bi0av
    content: ""
    status: pending
isProject: false
---

# Chess Coach LLM Agent -- План разработки

## Архитектура

```mermaid
flowchart TB
    subgraph frontend [React SPA]
        Upload[Upload PGN]
        Board[Chessboard Replay]
        Comments[Move Comments Panel]
        Reports[Period Reports]
    end

    subgraph backend [FastAPI Backend]
        API[REST API]
        PGNParser[PGN Parser Service]
        StockfishSvc[Stockfish Analyzer Service]
        LLMCoach[LLM Coach Service]
        ReviewOrch[Game Review Orchestrator]
        ReportSvc[Report Service]
    end

    subgraph external [External]
        Stockfish[Stockfish Engine]
        LiteLLM[LiteLLM - GPT-5.2]
        DB[(PostgreSQL)]
    end

    Upload --> API
    Board --> API
    Reports --> API
    API --> ReviewOrch
    ReviewOrch --> PGNParser
    ReviewOrch --> StockfishSvc
    ReviewOrch --> LLMCoach
    API --> ReportSvc
    ReportSvc --> LLMCoach
    StockfishSvc --> Stockfish
    LLMCoach --> LiteLLM
    ReviewOrch --> DB
    ReportSvc --> DB
```



## Data Flow -- анализ одной партии

```mermaid
sequenceDiagram
    participant U as User
    participant API as FastAPI
    participant PGN as PGNParser
    participant SF as StockfishAnalyzer
    participant LLM as LLMCoach
    participant DB as PostgreSQL

    U->>API: Upload PGN
    API->>PGN: Parse PGN file
    PGN-->>API: List of Game objects
    API->>DB: Save games metadata

    loop For each game
        API->>SF: Analyze all positions
        Note over SF: For each move:<br/>1. Eval position (depth 22)<br/>2. Top 5 candidate moves<br/>3. PV lines 10 moves deep<br/>4. Classify move quality
        SF-->>API: MoveAnalysis[] per game
        API->>DB: Save raw analysis
        API->>LLM: Send structured analysis
        Note over LLM: Generate per-move<br/>commentary + game summary
        LLM-->>API: TextCommentary[]
        API->>DB: Save LLM commentary
    end

    API-->>U: Analysis ready
```



## Стек технологий

### Backend (Python)

- **FastAPI** -- REST API
- **python-chess** -- PGN-парсинг, работа с позициями, интеграция со Stockfish через `chess.engine`
- **Stockfish** -- шахматный движок (бинарник, вызывается через python-chess UCI)
- **LiteLLM** -- абстракция для LLM (GPT-5.2)
- **SQLAlchemy 2.0** -- ORM (async)
- **Alembic** -- миграции БД
- **Pydantic v2** -- валидация и сериализация
- **Celery + Redis** -- фоновые задачи (анализ партий тяжёлый, 1-5 мин на партию)
- **UV** -- управление зависимостями (по правилам проекта)
- **Ruff** -- линтинг и форматирование

### Frontend

- **React 18** + **TypeScript**
- **react-chessboard** -- интерактивная доска
- **chess.js** -- логика шахмат на клиенте (валидация, навигация)
- **TanStack Query** -- управление серверным состоянием
- **Tailwind CSS** -- стилизация
- **Vite** -- сборка

### Infrastructure

- **PostgreSQL 16** -- основная БД
- **Redis** -- брокер задач для Celery
- **Docker Compose** -- локальный стек (Postgres, Redis, Stockfish)

---

## Структура проекта

```
chess-master/
├── src/
│   └── app/
│       ├── __init__.py
│       ├── main.py                    # FastAPI app factory
│       ├── core/
│       │   ├── config.py              # Settings (Pydantic BaseSettings)
│       │   ├── database.py            # Async SQLAlchemy engine/session
│       │   └── dependencies.py        # FastAPI DI
│       ├── models/
│       │   ├── game.py                # Game SQLAlchemy model
│       │   ├── move_analysis.py       # MoveAnalysis model
│       │   ├── game_analysis.py       # GameAnalysis (summary) model
│       │   └── period_report.py       # PeriodReport model
│       ├── schemas/
│       │   ├── game.py                # Pydantic schemas for API
│       │   ├── analysis.py
│       │   └── report.py
│       ├── services/
│       │   ├── pgn_parser.py          # PGN parsing via python-chess
│       │   ├── stockfish_analyzer.py  # Stockfish analysis engine
│       │   ├── llm_coach.py           # LLM commentary generation
│       │   ├── game_review.py         # Orchestrator: parse -> analyze -> LLM
│       │   └── report.py              # Period report generation
│       ├── api/
│       │   ├── router.py              # Main router
│       │   ├── games.py               # /api/games endpoints
│       │   ├── analysis.py            # /api/analysis endpoints
│       │   └── reports.py             # /api/reports endpoints
│       ├── tasks/
│       │   └── analysis.py            # Celery tasks for async analysis
│       └── utils/
│           ├── chess_helpers.py        # Move classification, FEN utils
│           └── llm_prompts.py         # Prompt templates for LLM coach
├── tests/
│   ├── conftest.py
│   ├── test_pgn_parser.py
│   ├── test_stockfish_analyzer.py
│   ├── test_llm_coach.py
│   └── test_api/
├── frontend/                          # React app (отдельный package.json)
│   ├── src/
│   │   ├── components/
│   │   │   ├── ChessBoard.tsx         # Board wrapper
│   │   │   ├── MoveList.tsx           # Move list with classifications
│   │   │   ├── CommentaryPanel.tsx    # LLM commentary per move
│   │   │   ├── GameUpload.tsx         # PGN upload form
│   │   │   └── ReportView.tsx         # Period reports
│   │   ├── pages/
│   │   ├── hooks/
│   │   └── api/
│   └── package.json
├── alembic/
│   └── versions/
├── pyproject.toml
├── uv.lock
└── docker-compose.yml
```

---

## Схема БД

```mermaid
erDiagram
    games {
        uuid id PK
        text pgn_text
        varchar white_player
        varchar black_player
        varchar result
        varchar opening_name
        varchar eco_code
        varchar time_control
        date played_at
        varchar player_color
        timestamp created_at
    }

    game_analyses {
        uuid id PK
        uuid game_id FK
        text summary
        text opening_assessment
        text middlegame_assessment
        text endgame_assessment
        jsonb key_moments
        float accuracy_white
        float accuracy_black
        varchar status
        timestamp created_at
    }

    move_analyses {
        uuid id PK
        uuid game_analysis_id FK
        int move_number
        varchar color
        varchar move_san
        varchar best_move_san
        float eval_before
        float eval_after
        float centipawn_loss
        varchar classification
        jsonb top_moves
        jsonb continuation_lines
        text llm_comment
        timestamp created_at
    }

    period_reports {
        uuid id PK
        date period_start
        date period_end
        varchar period_type
        text recommendations
        jsonb weakness_patterns
        jsonb strength_patterns
        jsonb game_ids
        timestamp created_at
    }

    games ||--o| game_analyses : has
    game_analyses ||--|{ move_analyses : contains
    period_reports }o--|{ games : references
```



---

## Ключевые сервисы -- детали реализации

### 1. StockfishAnalyzerService (`src/app/services/stockfish_analyzer.py`)

Ядро системы. Для каждого хода:

- Оценка позиции на глубине 22 (или time limit 5 сек)
- Получение top-5 ходов через `engine.analyse(board, limit, multipv=5)`
- Для каждого кандидата -- PV-линия на 10 ходов вперёд
- Классификация хода игрока по centipawn loss:
  - `|cp_loss| < 10` -- best
  - `|cp_loss| < 30` -- good
  - `|cp_loss| < 50` -- inaccuracy
  - `|cp_loss| < 100` -- mistake
  - `|cp_loss| >= 100` -- blunder

### 2. LLMCoachService (`src/app/services/llm_coach.py`)

Работает через LiteLLM. Три режима промптов:

- **Per-move commentary**: получает FEN, ход игрока, лучший ход движка, continuation lines, классификацию. Генерирует объяснение на 2-5 предложений.
- **Game summary**: получает все классификации ходов, ключевые моменты, opening/middlegame/endgame фазы. Генерирует сводку партии.
- **Period report**: получает сводки N партий за период. Выявляет паттерны ошибок, сильные стороны, даёт рекомендации для прогресса.

Промпты хранятся в `src/app/utils/llm_prompts.py` как шаблоны.

### 3. GameReviewService (`src/app/services/game_review.py`)

Оркестратор, управляет пайплайном:

1. Принимает PGN
2. Вызывает `PGNParserService` для парсинга
3. Запускает Celery-задачу для `StockfishAnalyzerService`
4. По завершении Stockfish-анализа передаёт данные в `LLMCoachService`
5. Сохраняет всё в БД
6. Уведомляет фронтенд о готовности (WebSocket или polling)

---

## API Endpoints

- `POST /api/games/upload` -- загрузка PGN (один или несколько файлов)
- `GET /api/games` -- список партий (фильтры: дата, результат, opening)
- `GET /api/games/{id}` -- детали партии
- `GET /api/games/{id}/analysis` -- полный анализ с комментариями к каждому ходу
- `GET /api/games/{id}/analysis/status` -- статус анализа (pending/in_progress/done)
- `POST /api/reports` -- генерация отчёта за период (body: start, end, period_type)
- `GET /api/reports/{id}` -- получение отчёта

---

## Frontend -- ключевые экраны

1. **Game Library** -- таблица партий, фильтры, кнопка Upload
2. **Game Viewer** -- главный экран:
  - Шахматная доска (react-chessboard) с анимацией ходов
  - Список ходов с цветовой индикацией (зелёный=best, жёлтый=inaccuracy, оранжевый=mistake, красный=blunder)
  - Панель комментария -- LLM-текст для текущего хода
  - Стрелки на доске для лучших ходов движка
  - Навигация: first/prev/next/last/autoplay
  - Eval bar (оценка позиции движком)
3. **Reports** -- сводки за период с рекомендациями

---

## Порядок разработки (фазы)

**Фаза 1 -- Foundation**: инициализация проекта, pyproject.toml, Docker Compose (Postgres + Redis), структура каталогов, модели БД, Alembic миграции, базовый FastAPI app.

**Фаза 2 -- Core Engine**: PGN-парсер, Stockfish-анализатор, сохранение результатов в БД. Celery для фоновых задач.

**Фаза 3 -- LLM Coach**: интеграция LiteLLM, промпты для per-move/game/period анализа, генерация текстовых комментариев.

**Фаза 4 -- API Layer**: REST endpoints для загрузки, получения анализа, генерации отчётов.

**Фаза 5 -- Frontend**: React app, шахматная доска, навигация по ходам, панель комментариев, загрузка PGN, список партий.

**Фаза 6 -- Reports**: агрегированная аналитика за период, рекомендации по прогрессу.

**Фаза 7 -- Polish**: тесты, обработка ошибок, оптимизация производительности Stockfish, streaming LLM ответов.