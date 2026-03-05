import { useQuery } from "@tanstack/react-query";
import * as api from "../api/client";

export function useAnalysis(gameId: string | null) {
  return useQuery({
    queryKey: ["analysis", gameId],
    queryFn: () => api.getAnalysis(gameId!),
    enabled: !!gameId,
  });
}

export function useAnalysisStatus(gameId: string | null) {
  return useQuery({
    queryKey: ["analysis-status", gameId],
    queryFn: () => api.getAnalysisStatus(gameId!),
    enabled: !!gameId,
    refetchInterval: (query) => {
      const status = query.state.data?.status;
      if (status === "pending" || status === "in_progress") {
        return 2000; // Poll every 2s while analyzing
      }
      return false;
    },
  });
}
