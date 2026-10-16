import { useQuery } from "@tanstack/react-query"
import { getJson } from "@/lib/api"
import type { HostsResponse, UsageResponse } from "./types"

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
