import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query"
import { getJson, postJson } from "@/lib/api"
import type { Brief, Today } from "./types"

export const todayKey = ["today"]

export function useToday() {
  return useQuery({
    queryKey: todayKey,
    queryFn: () => getJson<Today>("/api/today"),
    refetchInterval: 10000,
  })
}

function useGenerate(url: string) {
  const queryClient = useQueryClient()
  return useMutation({
    mutationFn: () => postJson<Brief>(url, {}),
    onSuccess: async () => {
      await queryClient.invalidateQueries({ queryKey: todayKey })
    },
  })
}

export function useRunBrief() {
  return useGenerate("/api/today/brief")
}

export function useRunDigest() {
  return useGenerate("/api/today/digest")
}
