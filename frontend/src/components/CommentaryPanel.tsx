import { useEffect, useState } from "react";
import * as api from "../api/client";
import type { MoveAnalysisRead } from "../api/types";

interface CommentaryPanelProps {
  gameId?: string;
  moveIndex: number | null;
  allowStreaming?: boolean;
  move: MoveAnalysisRead | null;
  summary?: string | null;
}

export function CommentaryPanel({
  gameId,
  moveIndex,
  allowStreaming = false,
  move,
  summary,
}: CommentaryPanelProps) {
  const [streamedComment, setStreamedComment] = useState<string | null>(null);
  const [isStreaming, setIsStreaming] = useState(false);

  useEffect(() => {
    setStreamedComment(null);
    setIsStreaming(false);

    if (!allowStreaming || !move || move.llm_comment || !gameId || moveIndex == null) return;

    let cancelled = false;
    const controller = new AbortController();
    setIsStreaming(true);

    void api
      .streamMoveCommentary(gameId, moveIndex, (chunk) => {
        if (cancelled) return;
        setStreamedComment((prev) => `${prev ?? ""}${chunk}`);
      }, controller.signal)
      .then((fullComment) => {
        if (cancelled || !fullComment) return;
        setStreamedComment((prev) => prev ?? fullComment);
      })
      .catch(() => {
        if (!cancelled) setStreamedComment(null);
      })
      .finally(() => {
        if (!cancelled) setIsStreaming(false);
      });

    return () => {
      cancelled = true;
      controller.abort();
    };
  }, [allowStreaming, gameId, moveIndex, move?.id, move?.llm_comment]);

  const comment = move?.llm_comment ?? streamedComment ?? null;

  return (
    <div className="rounded-lg border border-stone-300 bg-stone-200/50 p-4 dark:border-stone-600 dark:bg-chess-light/30">
      <h3 className="mb-3 text-sm font-semibold text-stone-600 dark:text-stone-400">Commentary</h3>
      <div className="space-y-3 text-sm text-stone-700 dark:text-stone-300">
        {move ? (
          <>
            <div className="flex flex-wrap gap-2">
              <span className="rounded bg-stone-300 px-2 py-0.5 dark:bg-stone-600/50">
                {move.move_san}
              </span>
              {move.best_move_san &&
                move.move_san !== move.best_move_san &&
                move.classification !== "theory" && (
                  <span className="text-stone-500">
                    Best: {move.best_move_san}
                  </span>
                )}
              {move.classification && (
                <span className="rounded border border-stone-400 px-2 py-0.5 capitalize text-stone-600 dark:border-stone-500/50 dark:text-stone-400">
                  {move.classification}
                </span>
              )}
            </div>
            {comment ? (
              <p className="leading-relaxed">{comment}</p>
            ) : isStreaming ? (
              <p className="italic text-stone-500">Generating commentary...</p>
            ) : (
              <p className="italic text-stone-500">No commentary for this move.</p>
            )}
          </>
        ) : summary ? (
          <p className="leading-relaxed">{summary}</p>
        ) : (
          <p className="italic text-stone-500">Select a move to view commentary.</p>
        )}
      </div>
    </div>
  );
}
