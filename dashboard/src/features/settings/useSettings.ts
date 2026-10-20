import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query"
import { getJson, postJson, putJson } from "@/lib/api"
import type { ClientRules, ModelOptions, SmokeResult } from "./types"

export const rulesKey = ["settings", "rules"]
export const modelsKey = ["settings", "models"]

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
