import { useQuery, useMutation, useQueryClient } from "@tanstack/react-query";
import * as api from "../api/client";

export function useReports(params?: Parameters<typeof api.listReports>[0]) {
  return useQuery({
    queryKey: ["reports", params],
    queryFn: () => api.listReports(params ?? {}),
  });
}

export function useReport(reportId: string | null) {
  return useQuery({
    queryKey: ["report", reportId],
    queryFn: () => api.getReport(reportId!),
    enabled: !!reportId,
  });
}

export function useCreateReport() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: (body: {
      period_start: string;
      period_end: string;
      period_type: "daily" | "weekly" | "monthly";
    }) => api.createReport(body),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ["reports"] });
    },
  });
}
