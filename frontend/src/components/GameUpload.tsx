import { useState, useRef } from "react";
import { useUploadPgn, useImportPgnText } from "../hooks/useGames";
import type { GameRead } from "../api/types";
import { ApiError } from "../api/client";

interface GameUploadProps {
  onUploaded?: (games: GameRead[]) => void;
}

type UploadMode = "file" | "paste";

export function GameUpload({ onUploaded }: GameUploadProps) {
  const [mode, setMode] = useState<UploadMode>("paste");
  const [playerColor, setPlayerColor] = useState<"white" | "black" | undefined>();
  const [pgnText, setPgnText] = useState("");
  const [error, setError] = useState<string | null>(null);
  const [importConflict, setImportConflict] = useState(false);
  const inputRef = useRef<HTMLInputElement>(null);

  const uploadFile = useUploadPgn();
  const importText = useImportPgnText();

  const isPending = uploadFile.isPending || importText.isPending;

  const handleFileSubmit = async (event: React.FormEvent) => {
    event.preventDefault();
    setError(null);
    setImportConflict(false);
    if (!playerColor) {
      setError("Выберите сторону, за которую вы играли");
      return;
    }
    const file = inputRef.current?.files?.[0];
    if (!file) {
      setError("Выберите PGN-файл");
      return;
    }
    try {
      const games = await uploadFile.mutateAsync({ file, playerColor });
      onUploaded?.(games);
      inputRef.current!.value = "";
    } catch (err) {
      setImportConflict(err instanceof ApiError && err.status === 409);
      setError(err instanceof Error ? err.message : "Не удалось загрузить файл");
    }
  };

  const handlePasteSubmit = async (event: React.FormEvent) => {
    event.preventDefault();
    setError(null);
    setImportConflict(false);
    if (!playerColor) {
      setError("Выберите сторону, за которую вы играли");
      return;
    }
    const text = pgnText.trim();
    if (!text) {
      setError("Вставьте текст PGN");
      return;
    }
    try {
      const games = await importText.mutateAsync({ pgnText: text, playerColor });
      onUploaded?.(games);
      setPgnText("");
    } catch (err) {
      setImportConflict(err instanceof ApiError && err.status === 409);
      setError(err instanceof Error ? err.message : "Не удалось импортировать PGN");
    }
  };

  const handleSubmit = mode === "file" ? handleFileSubmit : handlePasteSubmit;

  return (
    <form
      onSubmit={handleSubmit}
      className="rounded-lg border border-stone-300 bg-stone-200/50 p-6 dark:border-stone-600 dark:bg-chess-light/30"
    >
      <h3 className="mb-4 text-lg font-semibold text-stone-800 dark:text-stone-100">Импорт PGN</h3>

      <div className="mb-4 flex flex-wrap gap-2 border-b border-stone-300 pb-3 dark:border-stone-600">
        <button
          type="button"
          onClick={() => setMode("paste")}
          className={`rounded px-3 py-1.5 text-sm font-medium transition ${
            mode === "paste"
              ? "bg-chess-highlight text-stone-100"
              : "text-stone-600 hover:bg-stone-300 hover:text-stone-900 dark:text-stone-400 dark:hover:bg-stone-700 dark:hover:text-stone-200"
          }`}
        >
          Вставить текст
        </button>
        <button
          type="button"
          onClick={() => setMode("file")}
          className={`rounded px-3 py-1.5 text-sm font-medium transition ${
            mode === "file"
              ? "bg-chess-highlight text-stone-100"
              : "text-stone-600 hover:bg-stone-300 hover:text-stone-900 dark:text-stone-400 dark:hover:bg-stone-700 dark:hover:text-stone-200"
          }`}
        >
          Загрузить файл
        </button>
      </div>

      <div className="space-y-4">
        {mode === "paste" ? (
          <div>
            <label htmlFor="pgn-text" className="mb-2 block text-sm text-stone-600 dark:text-stone-400">
              Текст PGN
            </label>
            <textarea
              id="pgn-text"
              value={pgnText}
              onChange={(event) => setPgnText(event.target.value)}
              placeholder={`Вставьте PGN, например:\n[Event "Casual Game"]\n[White "Player1"]\n[Black "Player2"]\n[Result "1-0"]\n\n1. e4 e5 2. Nf3 Nc6 3. Bb5 a6...`}
              rows={10}
              className="w-full rounded border border-stone-400 bg-white px-3 py-2 font-mono text-sm text-stone-800 placeholder-stone-500 focus:border-chess-highlight focus:outline-none dark:border-stone-600 dark:bg-chess-dark dark:text-stone-200"
            />
          </div>
        ) : (
          <div>
            <label htmlFor="pgn-file" className="mb-2 block text-sm text-stone-600 dark:text-stone-400">PGN-файл</label>
            <input
              id="pgn-file"
              ref={inputRef}
              type="file"
              accept=".pgn,text/plain"
              className="block w-full text-sm text-stone-600 file:mr-4 file:rounded file:border-0 file:bg-chess-highlight file:px-4 file:py-2 file:text-stone-100 file:hover:bg-chess-highlight/80 dark:text-stone-300"
            />
          </div>
        )}

        <div>
          <label htmlFor="player-color" className="mb-2 block text-sm text-stone-600 dark:text-stone-400">Ваш цвет (обязательно)</label>
          <select
            id="player-color"
            required
            value={playerColor ?? ""}
            onChange={(event) =>
              setPlayerColor((event.target.value as "white" | "black" | "") || undefined)
            }
            className="w-full rounded border border-stone-400 bg-white px-4 py-2 text-stone-800 focus:border-chess-highlight focus:outline-none dark:border-stone-600 dark:bg-chess-dark dark:text-stone-200"
          >
            <option value="" disabled>Выберите вашу сторону</option>
            <option value="white">Белые</option>
            <option value="black">Черные</option>
          </select>
        </div>

        <p className="text-sm text-stone-600 dark:text-stone-400">Импорт сохраняет новую партию и ставит анализ движком в очередь. Объяснения выбранной стороны запускаются отдельно в просмотре.</p>
        {error && <p role="alert" className="break-words text-sm text-red-400">{error}</p>}
        {importConflict && onUploaded && <button type="button" onClick={() => onUploaded([])} className="rounded border border-stone-400 px-3 py-2 text-sm dark:border-stone-600">Найти сохранённую партию в библиотеке</button>}

        <button
          type="submit"
          disabled={isPending}
          className="rounded bg-chess-highlight px-4 py-2 font-medium text-stone-100 transition hover:bg-chess-highlight/80 disabled:opacity-50"
        >
          {isPending ? "Импорт..." : mode === "paste" ? "Импортировать" : "Загрузить"}
        </button>
      </div>
    </form>
  );
}
