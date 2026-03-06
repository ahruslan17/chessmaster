import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import * as api from "../api/client";

export function useGameNote(gameId: string | null) {
  return useQuery({
    queryKey: ["game-note", gameId],
    queryFn: () => api.getGameNote(gameId!),
    enabled: Boolean(gameId),
  });
}

export function useGameNotes(params?: Parameters<typeof api.listGameNotes>[0]) {
  return useQuery({
    queryKey: ["game-notes", params],
    queryFn: () => api.listGameNotes(params ?? {}),
  });
}

export function useUpsertGameNote() {
  const queryClient = useQueryClient();

  return useMutation({
    mutationFn: ({ gameId, content }: { gameId: string; content: string }) =>
      api.upsertGameNote(gameId, { content }),
    onSuccess: (note) => {
      queryClient.invalidateQueries({ queryKey: ["game-note", note.game_id] });
      queryClient.invalidateQueries({ queryKey: ["game-notes"] });
    },
  });
}
