import { useState } from "react"
import { PageHeader } from "@/components/PageHeader"
import { Button } from "@/components/ui/button"
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card"
import { Input } from "@/components/ui/input"
import { ScrollArea } from "@/components/ui/scroll-area"
import { useCalendar, useFindSlot, useRefreshCalendar } from "./useCalendar"

function day(value: string): string {
  return new Date(value).toLocaleDateString([], {
    weekday: "short",
    day: "numeric",
    month: "short",
  })
}

function clock(value: string): string {
  return new Date(value).toLocaleTimeString([], {
    hour: "2-digit",
    minute: "2-digit",
  })
}

export function CalendarPage() {
  const { data: events = [] } = useCalendar()
  const refresh = useRefreshCalendar()
  const findSlot = useFindSlot()
  const [minutes, setMinutes] = useState(30)

  return (
    <ScrollArea className="min-h-0 flex-1">
      <main className="mx-auto flex max-w-4xl flex-col gap-6 p-6">
        <PageHeader
          eyebrow="Schedule"
          title="Calendar"
          description="The next seven days, read from Google Calendar."
          actions={
            <Button
              size="sm"
              variant="outline"
              disabled={refresh.isPending}
              onClick={() => refresh.mutate()}
            >
              Refresh
            </Button>
          }
        />

        {refresh.error && (
          <p className="text-sm text-destructive">{refresh.error.message}</p>
        )}

        <div className="overflow-x-auto rounded-lg border border-border bg-card/60 shadow-[inset_0_1px_0_var(--marble-1)]">
          <table className="w-full text-sm">
            <thead className="border-b border-border bg-muted/40 text-left text-[9px] tracking-[0.22em] uppercase text-muted-foreground">
              <tr>
                <th className="px-3 py-2.5 font-medium">Day</th>
                <th className="px-3 py-2.5 font-medium">Time</th>
                <th className="px-3 py-2.5 font-medium">Event</th>
                <th className="px-3 py-2.5 font-medium">Location</th>
              </tr>
            </thead>
            <tbody>
              {events.map((event) => (
                <tr
                  key={event.event_id}
                  className="border-t border-border/70 transition-colors hover:bg-muted/30"
                >
                  <td className="px-3 py-2.5 whitespace-nowrap">
                    {day(event.start)}
                  </td>
                  <td className="px-3 py-2.5 whitespace-nowrap text-muted-foreground tabular-nums">
                    {clock(event.start)}–{clock(event.end)}
                  </td>
                  <td className="px-3 py-2.5">{event.title}</td>
                  <td className="px-3 py-2.5 text-muted-foreground">
                    {event.location}
                  </td>
                </tr>
              ))}
              {events.length === 0 && (
                <tr className="border-t border-border/70">
                  <td colSpan={4} className="px-3 py-6 text-muted-foreground">
                    No events in the next seven days.
                  </td>
                </tr>
              )}
            </tbody>
          </table>
        </div>

        <section className="flex flex-col gap-3">
          <h2 className="text-[9px] font-medium tracking-[0.3em] uppercase text-muted-foreground">
            Find a slot
          </h2>
          <div className="flex flex-wrap items-end gap-2">
            <label className="flex flex-col gap-1 text-[10px] tracking-[0.16em] uppercase text-muted-foreground">
              Minutes
              <Input
                type="number"
                min={5}
                max={240}
                value={minutes}
                onChange={(event) => setMinutes(Number(event.target.value))}
                className="w-24"
              />
            </label>
            <Button
              size="sm"
              disabled={findSlot.isPending || !minutes}
              onClick={() => findSlot.mutate(minutes)}
            >
              Propose three slots
            </Button>
          </div>
          {findSlot.error && (
            <p className="text-sm text-destructive">{findSlot.error.message}</p>
          )}
          {findSlot.data && findSlot.data.length === 0 && (
            <p className="text-sm text-muted-foreground">
              No free slots in the next week.
            </p>
          )}
          <div className="flex flex-col gap-2">
            {findSlot.data?.map((slot) => (
              <Card key={slot.start} size="sm">
                <CardHeader>
                  <CardTitle className="text-sm">
                    {day(slot.start)} · {clock(slot.start)}–{clock(slot.end)}
                  </CardTitle>
                </CardHeader>
                <CardContent>
                  <p className="text-xs leading-relaxed text-muted-foreground">
                    Free for {minutes} minutes. Create it from Chat so the
                    approval flow records the event.
                  </p>
                </CardContent>
              </Card>
            ))}
          </div>
        </section>
      </main>
    </ScrollArea>
  )
}
