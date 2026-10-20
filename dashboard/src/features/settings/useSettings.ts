import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query"
import { getJson, putJson } from "@/lib/api"
import type { ClientRules } from "./types"

export const rulesKey = ["settings", "rules"]

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
    },
  })
}
