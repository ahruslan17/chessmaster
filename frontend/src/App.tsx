import { BrowserRouter, Link, Navigate, Route, Routes, useParams } from "react-router-dom";

import { AccessGate, usePublicPreview } from "./components/AccessGate";
import { useTheme } from "./contexts/ThemeContext";
import { GameLibrary } from "./pages/GameLibrary";
import { GameViewer } from "./pages/GameViewer";
import { Openings } from "./pages/Openings";
import { Diary } from "./pages/Diary";

function ThemeToggle() {
  const { theme, toggleTheme } = useTheme();
  return (
    <button
      type="button"
      onClick={toggleTheme}
      className="rounded-lg p-2 text-stone-500 transition hover:bg-stone-200 hover:text-stone-800 dark:text-stone-300 dark:hover:bg-stone-700 dark:hover:text-stone-100"
      title={theme === "dark" ? "Переключить на светлую тему" : "Переключить на тёмную тему"}
      aria-label="Переключить тему"
    >
      {theme === "dark" ? (
        <svg className="h-5 w-5" fill="currentColor" viewBox="0 0 24 24" aria-hidden>
          <path d="M12 2.25a.75.75 0 0 1 .75.75v1.5a.75.75 0 0 1-1.5 0V3a.75.75 0 0 1 .75-.75ZM12 18a.75.75 0 0 1 .75.75v1.5a.75.75 0 0 1-1.5 0v-1.5A.75.75 0 0 1 12 18ZM2.25 12a.75.75 0 0 1 .75-.75h1.5a.75.75 0 0 1 0 1.5H3a.75.75 0 0 1-.75-.75ZM18 12a.75.75 0 0 1 .75-.75h1.5a.75.75 0 0 1 0 1.5h-1.5a.75.75 0 0 1-.75-.75ZM4.5 4.5a.75.75 0 0 1 1.06 0l1.06 1.06a.75.75 0 0 1-1.06 1.06L4.5 5.56a.75.75 0 0 1 0-1.06ZM18.44 18.44a.75.75 0 0 1 1.06 0l1.06 1.06a.75.75 0 1 1-1.06 1.06l-1.06-1.06a.75.75 0 0 1 0-1.06ZM4.5 19.5a.75.75 0 0 1 0-1.06l1.06-1.06a.75.75 0 1 1 1.06 1.06L5.56 19.5a.75.75 0 0 1-1.06 0ZM19.5 4.5a.75.75 0 0 1 0 1.06l-1.06 1.06a.75.75 0 0 1-1.06-1.06L18.44 4.5a.75.75 0 0 1 1.06 0ZM12 8.25a3.75 3.75 0 1 0 0 7.5 3.75 3.75 0 0 0 0-7.5Z" />
        </svg>
      ) : (
        <svg className="h-5 w-5" fill="currentColor" viewBox="0 0 24 24" aria-hidden>
          <path d="M12 3a9 9 0 1 0 9 9c0-.46-.04-.92-.1-1.36a5.39 5.39 0 0 1-4.4 2.26 5.403 5.403 0 0 1-3.14-9.8c-.44-.06-.9-.1-1.36-.1z" />
        </svg>
      )}
    </button>
  );
}

export default function App() {
  return (
    <AccessGate>
      <Application />
    </AccessGate>
  );
}

function Application() {
  const publicPreview = usePublicPreview();

  return (
    <BrowserRouter>
      <div className="min-h-screen bg-stone-100 text-stone-800 dark:bg-chess-dark dark:text-stone-200">
        <header className="border-b border-stone-300 bg-stone-200/80 px-3 py-4 sm:px-6 dark:border-stone-700 dark:bg-chess-light">
          <nav className="mx-auto flex max-w-7xl flex-wrap items-center justify-between gap-3">
            <Link to="/" className="text-xl font-semibold text-stone-800 dark:text-stone-100">
              Chess Master
            </Link>
            <div className="flex flex-wrap items-center gap-3">
              <Link
                to="/"
                className="text-stone-600 transition hover:text-stone-900 dark:text-stone-200 dark:hover:text-stone-100"
              >
                Партии
              </Link>
              <Link
                to="/openings"
                className="text-stone-600 transition hover:text-stone-900 dark:text-stone-200 dark:hover:text-stone-100"
              >
                Дебюты
              </Link>
              {!publicPreview && (
                <Link
                  to="/diary"
                  className="text-stone-600 transition hover:text-stone-900 dark:text-stone-200 dark:hover:text-stone-100"
                >
                  Дневник
                </Link>
              )}
              <ThemeToggle />
            </div>
          </nav>
        </header>

        <main className="mx-auto max-w-7xl px-3 py-6 sm:px-6 sm:py-8">
          <Routes>
            <Route path="/" element={<GameLibrary />} />
            <Route path="/games/:gameId" element={<GameViewerRoute />} />
            <Route path="/openings" element={<Openings />} />
            <Route
              path="/diary"
              element={publicPreview ? <Navigate to="/" replace /> : <Diary />}
            />
            <Route path="/reports" element={<Navigate to={publicPreview ? "/" : "/diary"} replace />} />
            <Route path="*" element={<Navigate to="/" replace />} />
          </Routes>
        </main>
      </div>
      </BrowserRouter>
  );
}

function GameViewerRoute() {
  const { gameId } = useParams<{ gameId: string }>();
  return <GameViewer key={gameId} />;
}
