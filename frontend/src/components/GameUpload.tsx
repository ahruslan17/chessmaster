import { useState, useRef } from "react";
import { useUploadPgn, useImportPgnText } from "../hooks/useGames";
import type { GameRead } from "../api/types";

interface GameUploadProps {
  onUploaded?: (games: GameRead[]) => void;
}

type UploadMode = "file" | "paste";

export function GameUpload({ onUploaded }: GameUploadProps) {
  const [mode, setMode] = useState<UploadMode>("paste");
  const [playerColor, setPlayerColor] = useState<"white" | "black" | undefined>();
  const [pgnText, setPgnText] = useState("");
  const [error, setError] = useState<string | null>(null);
  const inputRef = useRef<HTMLInputElement>(null);

  const uploadFile = useUploadPgn();
  const importText = useImportPgnText();

  const isPending = uploadFile.isPending || importText.isPending;

  const handleFileSubmit = async (e: React.FormEvent) => {
    e.preventDefault();
    setError(null);
    const file = inputRef.current?.files?.[0];
    if (!file) {
      setError("Please select a PGN file");
      return;
    }
    try {
      const games = await uploadFile.mutateAsync({ file, playerColor });
      onUploaded?.(games);
      inputRef.current!.value = "";
    } catch (err) {
      setError(err instanceof Error ? err.message : "Upload failed");
    }
  };

  const handlePasteSubmit = async (e: React.FormEvent) => {
    e.preventDefault();
    setError(null);
    const text = pgnText.trim();
    if (!text) {
      setError("Please paste PGN text");
      return;
    }
    try {
      const games = await importText.mutateAsync({ pgnText: text, playerColor });
      onUploaded?.(games);
      setPgnText("");
    } catch (err) {
      setError(err instanceof Error ? err.message : "Import failed");
    }
  };

  const handleSubmit = mode === "file" ? handleFileSubmit : handlePasteSubmit;

  return (
    <form
      onSubmit={handleSubmit}
      className="rounded-lg border border-stone-300 bg-stone-200/50 p-6 dark:border-stone-600 dark:bg-chess-light/30"
    >
      <h3 className="mb-4 text-lg font-semibold text-stone-800 dark:text-stone-100">Import PGN</h3>

      <div className="mb-4 flex gap-2 border-b border-stone-300 pb-3 dark:border-stone-600">
        <button
          type="button"
          onClick={() => setMode("paste")}
          className={`rounded px-3 py-1.5 text-sm font-medium transition ${
            mode === "paste"
              ? "bg-chess-highlight text-stone-100"
              : "text-stone-600 hover:bg-stone-300 hover:text-stone-900 dark:text-stone-400 dark:hover:bg-stone-700 dark:hover:text-stone-200"
          }`}
        >
          Paste text
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
          Upload file
        </button>
      </div>

      <div className="space-y-4">
        {mode === "paste" ? (
          <div>
            <label className="mb-2 block text-sm text-stone-600 dark:text-stone-400">
              PGN text — paste your game
            </label>
            <textarea
              value={pgnText}
              onChange={(e) => setPgnText(e.target.value)}
              placeholder={`Paste PGN here, e.g.:\n[Event "Casual Game"]\n[White "Player1"]\n[Black "Player2"]\n[Result "1-0"]\n\n1. e4 e5 2. Nf3 Nc6 3. Bb5 a6...`}
              rows={10}
              className="w-full rounded border border-stone-400 bg-white px-3 py-2 font-mono text-sm text-stone-800 placeholder-stone-500 focus:border-chess-highlight focus:outline-none dark:border-stone-600 dark:bg-chess-dark dark:text-stone-200"
            />
          </div>
        ) : (
          <div>
            <label className="mb-2 block text-sm text-stone-600 dark:text-stone-400">PGN File</label>
            <input
              ref={inputRef}
              type="file"
              accept=".pgn,text/plain"
              className="block w-full text-sm text-stone-600 file:mr-4 file:rounded file:border-0 file:bg-chess-highlight file:px-4 file:py-2 file:text-stone-100 file:hover:bg-chess-highlight/80 dark:text-stone-300"
            />
          </div>
        )}

        <div>
          <label className="mb-2 block text-sm text-stone-600 dark:text-stone-400">Your color (optional)</label>
          <select
            value={playerColor ?? ""}
            onChange={(e) =>
              setPlayerColor((e.target.value as "white" | "black" | "") || undefined)
            }
            className="w-full rounded border border-stone-400 bg-white px-4 py-2 text-stone-800 focus:border-chess-highlight focus:outline-none dark:border-stone-600 dark:bg-chess-dark dark:text-stone-200"
          >
            <option value="">Any</option>
            <option value="white">White</option>
            <option value="black">Black</option>
          </select>
        </div>

        {error && <p className="text-sm text-red-400">{error}</p>}

        <button
          type="submit"
          disabled={isPending}
          className="rounded bg-chess-highlight px-4 py-2 font-medium text-stone-100 transition hover:bg-chess-highlight/80 disabled:opacity-50"
        >
          {isPending ? "Importing..." : mode === "paste" ? "Import" : "Upload"}
        </button>
      </div>
    </form>
  );
}
