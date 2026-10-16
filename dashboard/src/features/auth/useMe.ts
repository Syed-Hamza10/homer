import { useQuery } from "@tanstack/react-query"
import { getJson } from "@/lib/api"

export function useMe() {
  return useQuery({
    queryKey: ["auth", "me"],
    queryFn: () => getJson<Record<string, unknown>>("/api/auth/me"),
    staleTime: Infinity,
  })
}
