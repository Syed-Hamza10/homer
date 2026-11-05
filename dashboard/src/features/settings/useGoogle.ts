import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query"
import { getJson, postJson } from "@/lib/api"
import type { GoogleStatus } from "./types"

export const googleKey = ["google", "status"]
const POLL_MS = 2000

export function useGoogleStatus() {
  return useQuery({
    queryKey: googleKey,
    queryFn: () => getJson<GoogleStatus>("/api/google/status"),
    refetchInterval: (query) =>
      query.state.data?.connecting ? POLL_MS : false,
  })
}

export function useConnectGoogle() {
  const queryClient = useQueryClient()
  return useMutation({
    mutationFn: () => postJson<GoogleStatus>("/api/google/connect", {}),
    onSuccess: (status) => queryClient.setQueryData(googleKey, status),
  })
}
