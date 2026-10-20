import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query"
import { getJson, postJson, putJson } from "@/lib/api"
import type {
  HostsResponse,
  UsageResponse,
  WebSearchResponse,
  WipeResponse,
} from "./types"

export function useHosts() {
  return useQuery({
    queryKey: ["privacy", "hosts"],
    queryFn: () => getJson<HostsResponse>("/api/privacy/hosts"),
    refetchInterval: 5000,
  })
}

export function useUsage() {
  return useQuery({
    queryKey: ["privacy", "usage"],
    queryFn: () => getJson<UsageResponse>("/api/privacy/usage"),
    refetchInterval: 5000,
  })
}

export function useSetWebSearch() {
  const queryClient = useQueryClient()
  return useMutation({
    mutationFn: (enabled: boolean) =>
      putJson<WebSearchResponse>("/api/privacy/web-search", { enabled }),
    onSuccess: async () => {
      await queryClient.invalidateQueries({ queryKey: ["privacy", "hosts"] })
    },
  })
}

export function useWipe() {
  const queryClient = useQueryClient()
  return useMutation({
    mutationFn: () =>
      postJson<WipeResponse>("/api/privacy/wipe", { confirm: true }),
    onSuccess: async () => {
      await queryClient.invalidateQueries()
    },
  })
}
