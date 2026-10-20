import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query"
import { getJson, postJson } from "@/lib/api"
import type { Event, Slot } from "./types"

export const calendarKey = ["calendar"]

export function useCalendar() {
  return useQuery({
    queryKey: calendarKey,
    queryFn: () => getJson<Event[]>("/api/calendar?days=7"),
    refetchInterval: 30000,
  })
}

export function useRefreshCalendar() {
  const queryClient = useQueryClient()
  return useMutation({
    mutationFn: () => postJson<Event[]>("/api/calendar/refresh", {}),
    onSuccess: async () => {
      await queryClient.invalidateQueries({ queryKey: calendarKey })
    },
  })
}

export function useFindSlot() {
  return useMutation({
    mutationFn: (minutes: number) =>
      postJson<Slot[]>("/api/calendar/find-slot", {
        duration_minutes: minutes,
      }),
  })
}
