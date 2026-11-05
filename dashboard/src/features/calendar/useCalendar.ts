import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query"
import { getJson, patchJson, postJson } from "@/lib/api"
import type { Approval } from "@/features/approvals/types"
import type { EventFields, EventRange, Slot } from "./types"

export const eventsKey = ["calendar", "events"]

export function useEvents(start: Date, end: Date) {
  const from = start.toISOString()
  const to = end.toISOString()
  return useQuery({
    queryKey: [...eventsKey, from, to],
    queryFn: () =>
      getJson<EventRange>(
        `/api/calendar/events?start=${encodeURIComponent(from)}&end=${encodeURIComponent(to)}`,
      ),
    refetchOnWindowFocus: true,
    refetchInterval: 120000,
  })
}

export function useRefreshEvents() {
  const queryClient = useQueryClient()
  return () => queryClient.invalidateQueries({ queryKey: eventsKey })
}

export function useCreateEvent() {
  return useMutation({
    mutationFn: (fields: EventFields) =>
      postJson<Approval>("/api/calendar/events", fields),
  })
}

export function useUpdateEvent() {
  return useMutation({
    mutationFn: ({
      id,
      change,
    }: {
      id: string
      change: Partial<EventFields>
    }) =>
      patchJson<Approval>(
        `/api/calendar/events/${encodeURIComponent(id)}`,
        change,
      ),
  })
}

export function useCancelEvent() {
  return useMutation({
    mutationFn: (id: string) =>
      postJson<Approval>(
        `/api/calendar/events/${encodeURIComponent(id)}/cancel`,
        {},
      ),
  })
}

export function useFindTimes() {
  return useMutation({
    mutationFn: (args: { minutes: number; attendees: string[] }) =>
      postJson<Slot[]>("/api/calendar/find-slot", {
        duration_minutes: args.minutes,
        days: 14,
        attendees: args.attendees,
        limit: 6,
      }),
  })
}
