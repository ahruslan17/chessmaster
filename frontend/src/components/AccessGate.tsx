import {
  createContext,
  useContext,
  useEffect,
  useState,
  type FormEvent,
  type ReactNode,
} from "react";

import { activateAccess, ApiError, getAccessConfig, getAccessStatus } from "../api/client";
import type { AccessStatusRead } from "../api/types";

type GateState = "loading" | "open" | "locked" | "error";
const PublicPreviewContext = createContext(false);

export function usePublicPreview(): boolean {
  return useContext(PublicPreviewContext);
}

export function AccessGate({ children }: { children: ReactNode }) {
  const [state, setState] = useState<GateState>("loading");
  const [publicPreview, setPublicPreview] = useState(false);

  useEffect(() => {
    let cancelled = false;
    void (async () => {
      try {
        const config = await getAccessConfig();
        if (!cancelled) setPublicPreview(config.enabled);
        if (!config.enabled) {
          if (!cancelled) setState("open");
          return;
        }
        const nextStatus = await getAccessStatus();
        if (!cancelled) {
          setState(nextStatus.active ? "open" : "locked");
        }
      } catch {
        if (!cancelled) setState("error");
      }
    })();
    return () => {
      cancelled = true;
    };
  }, []);

  if (state === "open") {
    return (
      <PublicPreviewContext.Provider value={publicPreview}>
        {children}
      </PublicPreviewContext.Provider>
    );
  }
  if (state === "locked") {
    return <AccessForm onActivated={() => setState("open")} />;
  }
  return (
    <main className="flex min-h-screen items-center justify-center bg-chess-dark px-6 py-10 text-stone-200">
      <div className="w-full max-w-xl rounded-lg border border-stone-600 bg-chess-light/30 p-6 text-center">
        <p className="text-sm text-stone-300">
          {state === "error" ? "Не удалось проверить доступ. Обновите страницу." : "Проверяем доступ..."}
        </p>
      </div>
    </main>
  );
}

function AccessForm({ onActivated }: { onActivated: (status: AccessStatusRead) => void }) {
  const [code, setCode] = useState("");
  const [error, setError] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);

  const submit = async (event: FormEvent) => {
    event.preventDefault();
    setError(null);
    setBusy(true);
    try {
      onActivated(await activateAccess(code));
    } catch (err) {
      setError(
        err instanceof ApiError && err.status === 401
          ? "Код недействителен или уже использован."
          : "Не удалось проверить код. Повторите попытку."
      );
    } finally {
      setBusy(false);
    }
  };

  return (
    <main className="flex min-h-screen items-center justify-center bg-chess-dark px-6 py-10 text-stone-200">
      <form
        onSubmit={submit}
        className="w-full max-w-xl rounded-lg border border-stone-600 bg-chess-light/30 p-6"
      >
        <h1 className="text-2xl font-semibold text-stone-100">Chess Master</h1>
        <p className="mt-3 text-sm leading-relaxed text-stone-300">
          Введите одноразовый код. После активации доступ к вашей гостевой сессии действует 15 минут.
        </p>
        <label htmlFor="access-code" className="mt-5 block text-sm text-stone-400">
          Код доступа
        </label>
        <input
          id="access-code"
          value={code}
          onChange={(event) => setCode(event.target.value.toUpperCase())}
          autoComplete="one-time-code"
          autoCapitalize="characters"
          spellCheck={false}
          placeholder="ABCD-EFGH-JKLM"
          className="mt-1 w-full rounded border border-stone-600 bg-chess-dark px-3 py-2 font-mono text-stone-200 placeholder-stone-500 focus:border-chess-highlight focus:outline-none"
        />
        {error && <p role="alert" className="mt-3 text-sm text-red-400">{error}</p>}
        <button
          type="submit"
          disabled={busy || !code.trim()}
          className="mt-5 rounded bg-chess-highlight px-4 py-2 font-medium text-stone-100 transition hover:bg-chess-highlight/80 disabled:opacity-50"
        >
          {busy ? "Проверяем..." : "Открыть Chess Master"}
        </button>
      </form>
    </main>
  );
}
