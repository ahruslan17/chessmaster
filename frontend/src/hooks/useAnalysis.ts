import { useQuery } from "@tanstack/react-query";
import * as api from "../api/client";
import type { PlayerColor } from "../api/types";

export function useAnalysis(gameId: string | null, pollWhileRunning = false, playerColor?: PlayerColor) {
  return useQuery({
    queryKey: ["analysis", gameId, playerColor],
    queryFn: () => api.getAnalysis(gameId!, playerColor),
    enabled: !!gameId,
    staleTime: 0,
    refetchOnMount: "always",
    retry: (count, error) => !(error instanceof api.ApiError && error.status === 404) && count < 2,
    refetchInterval: pollWhileRunning ? 2000 : false,
  });
}

export function useAnalysisStatus(gameId: string | null, playerColor?: PlayerColor) {
  return useQuery({
    queryKey: ["analysis-status", gameId, playerColor],
    queryFn: () => api.getAnalysisStatus(gameId!, playerColor),
    enabled: !!gameId,
    staleTime: 0,
    refetchOnMount: "always",
    refetchInterval: (query) => {
      const data = query.state.data;
      const status = data?.engine_status ?? data?.status;
      if (status === "queued" || status === "in_progress" || data?.review_status === "queued" || data?.review_status === "in_progress") {
        return 2000; // Poll every 2s while analyzing
      }
      return false;
    },
  });
}
