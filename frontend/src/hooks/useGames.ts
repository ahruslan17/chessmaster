import { useQuery, useMutation, useQueryClient } from "@tanstack/react-query";
import * as api from "../api/client";
export function useGames(params?: Parameters<typeof api.listGames>[0]) {
  return useQuery({
    queryKey: ["games", params],
    queryFn: () => api.listGames(params ?? {}),
  });
}

export function useGame(gameId: string | null) {
  return useQuery({
    queryKey: ["game", gameId],
    queryFn: () => api.getGame(gameId!),
    enabled: !!gameId,
  });
}

export function useUploadPgn() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: ({
      file,
      playerColor,
    }: {
      file: File;
      playerColor?: "white" | "black";
    }) => api.uploadPgn(file, playerColor),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ["games"] });
    },
  });
}

export function useImportPgnText() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: ({
      pgnText,
      playerColor,
    }: {
      pgnText: string;
      playerColor?: "white" | "black";
    }) => api.importPgnText(pgnText, playerColor),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ["games"] });
    },
  });
}
