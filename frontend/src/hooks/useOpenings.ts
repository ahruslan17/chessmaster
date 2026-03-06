import { useQuery } from "@tanstack/react-query";
import * as api from "../api/client";

export function useOpenings(params?: Parameters<typeof api.listOpenings>[0]) {
  return useQuery({
    queryKey: ["openings", params],
    queryFn: () => api.listOpenings(params ?? { limit: 5000 }),
  });
}
