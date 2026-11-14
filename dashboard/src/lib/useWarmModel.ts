import { useQuery } from "@tanstack/react-query"
import { post } from "./api"

export const WARM_MS = 4 * 60_000

export function useWarmModel() {
  useQuery({
    queryKey: ["model-warm"],
    queryFn: async () => {
      await post("/api/model/warm", {})
      return Date.now()
    },
    refetchInterval: WARM_MS,
    refetchIntervalInBackground: false,
    refetchOnWindowFocus: false,
    staleTime: WARM_MS,
    retry: false,
  })
}
