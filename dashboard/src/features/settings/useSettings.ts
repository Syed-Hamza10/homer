import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query"
import { getJson, postJson, putJson } from "@/lib/api"
import type { ClientRules, Health, ModelOptions, SmokeResult } from "./types"

export const rulesKey = ["settings", "rules"]
export const modelsKey = ["settings", "models"]
export const healthKey = ["health"]

export function useHealth() {
  return useQuery({
    queryKey: healthKey,
    queryFn: () => getJson<Health>("/api/health"),
    refetchInterval: 30000,
  })
}

export function useRules() {
  return useQuery({
    queryKey: rulesKey,
    queryFn: () => getJson<ClientRules>("/api/settings"),
  })
}

export function useSaveRules() {
  const queryClient = useQueryClient()
  return useMutation({
    mutationFn: (rules: ClientRules) =>
      putJson<ClientRules>("/api/settings", rules),
    onSuccess: async () => {
      await queryClient.invalidateQueries({ queryKey: rulesKey })
      await queryClient.invalidateQueries({ queryKey: modelsKey })
      await queryClient.invalidateQueries({ queryKey: healthKey })
    },
  })
}

export function useModelOptions() {
  return useQuery({
    queryKey: modelsKey,
    queryFn: () => getJson<ModelOptions>("/api/settings/models"),
  })
}

export function useSmoke() {
  return useMutation({
    mutationFn: (tier: string | null) =>
      postJson<SmokeResult>(
        `/api/settings/smoke${tier ? `?tier=${tier}` : ""}`,
        {},
      ),
  })
}
