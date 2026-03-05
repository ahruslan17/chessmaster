import { useState } from "react";
import { useNavigate } from "react-router-dom";
import { useGames } from "../hooks/useGames";
import { GameUpload } from "../components/GameUpload";
import type { GameListItem, GameRead } from "../api/types";

export function GameLibrary() {
  const navigate = useNavigate();
  const [showUpload, setShowUpload] = useState(false);
  const [resultFilter, setResultFilter] = useState<string>("");
  const [openingFilter, setOpeningFilter] = useState("");

  const { data: games = [], isLoading } = useGames({
    result: resultFilter || undefined,
    opening_name: openingFilter || undefined,
  });

  const handleUploaded = (uploaded: GameRead[]) => {
    setShowUpload(false);
    if (uploaded.length > 0) {
      navigate(`/games/${uploaded[0].id}`);
    }
  };

  return (
    <div className="space-y-6">
      <div className="flex items-center justify-between">
        <h1 className="text-2xl font-semibold text-stone-800 dark:text-stone-100">Game Library</h1>
        <button
          onClick={() => setShowUpload((s) => !s)}
          className="rounded bg-chess-highlight px-4 py-2 font-medium text-stone-100 transition hover:bg-chess-highlight/80"
        >
          {showUpload ? "Cancel" : "Upload PGN"}
        </button>
      </div>

      {showUpload && (
        <GameUpload onUploaded={handleUploaded} />
      )}

      <div className="flex flex-wrap gap-4">
        <div>
          <label className="mb-1 block text-sm text-stone-500">Result</label>
          <select
            value={resultFilter}
            onChange={(e) => setResultFilter(e.target.value)}
            className="rounded border border-stone-400 bg-white px-3 py-2 text-stone-800 focus:border-chess-highlight focus:outline-none dark:border-stone-600 dark:bg-chess-dark dark:text-stone-200"
          >
            <option value="">All</option>
            <option value="1-0">1-0 (White wins)</option>
            <option value="0-1">0-1 (Black wins)</option>
            <option value="1/2-1/2">1/2-1/2 (Draw)</option>
            <option value="*">* (Ongoing)</option>
          </select>
        </div>
        <div>
          <label className="mb-1 block text-sm text-stone-500">Opening</label>
          <input
            type="text"
            value={openingFilter}
            onChange={(e) => setOpeningFilter(e.target.value)}
            placeholder="Filter by opening..."
            className="rounded border border-stone-400 bg-white px-3 py-2 text-stone-800 placeholder-stone-500 focus:border-chess-highlight focus:outline-none dark:border-stone-600 dark:bg-chess-dark dark:text-stone-200"
          />
        </div>
      </div>

      {isLoading ? (
        <p className="py-8 text-center text-stone-500">Loading games...</p>
      ) : games.length === 0 ? (
        <div className="rounded-lg border border-stone-300 bg-stone-200/50 py-12 text-center dark:border-stone-600 dark:bg-chess-light/20">
          <p className="text-stone-600 dark:text-stone-500">No games yet. Upload a PGN file to get started.</p>
          <button
            onClick={() => setShowUpload(true)}
            className="mt-4 text-chess-highlight hover:underline"
          >
            Upload PGN
          </button>
        </div>
      ) : (
        <div className="overflow-hidden rounded-lg border border-stone-300 dark:border-stone-600">
          <table className="w-full">
            <thead>
              <tr className="border-b border-stone-300 bg-stone-200/80 dark:border-stone-600 dark:bg-chess-light/50">
                <th className="px-4 py-3 text-left text-sm font-medium text-stone-600 dark:text-stone-400">White</th>
                <th className="px-4 py-3 text-left text-sm font-medium text-stone-600 dark:text-stone-400">Black</th>
                <th className="px-4 py-3 text-left text-sm font-medium text-stone-600 dark:text-stone-400">Result</th>
                <th className="px-4 py-3 text-left text-sm font-medium text-stone-600 dark:text-stone-400">Opening</th>
                <th className="px-4 py-3 text-left text-sm font-medium text-stone-600 dark:text-stone-400">Date</th>
                <th className="px-4 py-3" />
              </tr>
            </thead>
            <tbody>
              {games.map((g) => (
                <GameRow key={g.id} game={g} onSelect={() => navigate(`/games/${g.id}`)} />
              ))}
            </tbody>
          </table>
        </div>
      )}
    </div>
  );
}

function GameRow({
  game,
  onSelect,
}: {
  game: GameListItem;
  onSelect: () => void;
}) {
  const openingText =
    game.eco_code && game.opening_name
      ? `${game.eco_code}: ${game.opening_name}`
      : game.opening_name || game.eco_code || "—";

  return (
    <tr
      onClick={onSelect}
      className="cursor-pointer border-b border-stone-200 transition hover:bg-stone-100 dark:border-stone-600/50 dark:hover:bg-chess-light/30"
    >
      <td className="px-4 py-3 text-stone-800 dark:text-stone-200">{game.white_player || "—"}</td>
      <td className="px-4 py-3 text-stone-800 dark:text-stone-200">{game.black_player || "—"}</td>
      <td className="px-4 py-3 text-stone-600 dark:text-stone-400">{game.result}</td>
      <td className="px-4 py-3 text-stone-600 dark:text-stone-400">{openingText}</td>
      <td className="px-4 py-3 text-stone-500">
        {game.played_at ? new Date(game.played_at).toLocaleDateString() : "—"}
      </td>
      <td className="px-4 py-3">
        <button
          onClick={(e) => {
            e.stopPropagation();
            onSelect();
          }}
          className="text-chess-highlight hover:underline"
        >
          View
        </button>
      </td>
    </tr>
  );
}
