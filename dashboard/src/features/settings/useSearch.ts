import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query"
import { getJson, postJson, putJson } from "@/lib/api"
import type { SearchProbe, SearchSettings, SearchUpdate } from "./types"

export const searchKey = ["settings", "search"]

export function useSearchSettings() {
  return useQuery({
    queryKey: searchKey,
    queryFn: () => getJson<SearchSettings>("/api/settings/search"),
  })
}

export function useSaveSearch() {
  const queryClient = useQueryClient()
  return useMutation({
    mutationFn: (update: SearchUpdate) =>
      putJson<SearchSettings>("/api/settings/search", update),
    onSuccess: (saved) => {
      queryClient.setQueryData(searchKey, saved)
      void queryClient.invalidateQueries({ queryKey: ["privacy", "hosts"] })
    },
  })
}

export function useTestSearch() {
  return useMutation({
    mutationFn: () => postJson<SearchProbe>("/api/settings/search/test", {}),
  })
}
