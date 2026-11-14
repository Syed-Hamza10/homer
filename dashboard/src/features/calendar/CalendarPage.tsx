import { Keyboard } from "lucide-react"
import { useState } from "react"
import { PageHeader } from "@/components/PageHeader"
import { ShortcutsHelp } from "@/components/ShortcutsHelp"
import { UpdatedAt } from "@/components/UpdatedAt"

import { Button } from "@/components/ui/button"
import type { Approval } from "@/features/approvals/types"
import { useTimezone } from "@/features/settings/useTimezone"
import { useShortcuts } from "@/lib/shortcuts"
import { useUrlParams } from "@/lib/useUrlParams"
import {
  dateKey,
  instantOf,
  wallString,
  wallTime,
  type WallTime,
} from "@/lib/zoned"
import { ApprovalPanel } from "./ApprovalPanel"
import { CalendarToolbar } from "./CalendarToolbar"
import { errorText } from "@/lib/errorText"
import { EventPopover } from "./EventPopover"
import { FindTimePanel } from "./FindTimePanel"
import { fromInstants, fromWalls } from "./formValue"
import { MonthGrid } from "./MonthGrid"
import { QuickCreate } from "./QuickCreate"
import {
  dateParam,
  rangeOf,
  rangeTitle,
  shift,
  viewParam,
  visibleDays,
} from "./range"
import { calendarShortcuts } from "./shortcuts"
import { TimeGrid } from "./TimeGrid"
import type { CalendarEvent, DateOnly, FormValue, View } from "./types"
import { useEvents, useRefreshEvents, useUpdateEvent } from "./useCalendar"
import { useNow } from "./useNow"

type Panel =
  | { kind: "event"; event: CalendarEvent }
  | { kind: "create"; initial: FormValue }
  | { kind: "approval"; approval: Approval }
  | null

const NARROW = "(max-width: 767px)"
const HOUR_MS = 3_600_000
const QUICK_MS = 1_800_000

function initialView(): View {
  return typeof window !== "undefined" && window.matchMedia?.(NARROW).matches
    ? "day"
    : "week"
}

function dateOnly(wall: WallTime): DateOnly {
  return { year: wall.year, month: wall.month, day: wall.day }
}

export function CalendarPage() {
  const timeZone = useTimezone()
  const now = useNow()
  const [params, navigate] = useUrlParams()
  const view = viewParam(params.get("view")) ?? initialView()
  const picked = dateParam(params.get("date"))
  const setView = (next: View) => navigate({ view: next }, true)
  const setPicked = (day: DateOnly | null) =>
    navigate({ date: day ? dateKey(day) : null }, true)
  const [panel, setPanel] = useState<Panel>(null)
  const [finding, setFinding] = useState(false)
  const [help, setHelp] = useState(false)
  const anchor = picked ?? dateOnly(wallTime(now, timeZone))
  const days = visibleDays(view, anchor)
  const range = rangeOf(days, timeZone)
  const { data, isPending, error, dataUpdatedAt } = useEvents(
    range.start,
    range.end,
  )
  const refresh = useRefreshEvents()
  const move = useUpdateEvent()
  const events = data?.events ?? []
  const showApproval = (approval: Approval) =>
    setPanel({ kind: "approval", approval })
  const create = (initial: FormValue) => setPanel({ kind: "create", initial })
  const step = (by: number) => setPicked(shift(view, anchor, by))
  const createNextHour = () => {
    const opens =
      instantOf({ ...wallTime(now, timeZone), minute: 0 }, timeZone).getTime() +
      HOUR_MS
    create(fromInstants(new Date(opens), new Date(opens + QUICK_MS), timeZone))
  }

  useShortcuts(
    help
      ? {}
      : {
          t: () => setPicked(null),
          d: () => setView("day"),
          w: () => setView("week"),
          m: () => setView("month"),
          j: () => step(1),
          ArrowRight: () => step(1),
          k: () => step(-1),
          ArrowLeft: () => step(-1),
          c: createNextHour,
          "?": () => setHelp(true),
        },
  )

  const side = (
    <>
      {panel?.kind === "event" && (
        <EventPopover
          key={panel.event.id}
          event={panel.event}
          timeZone={timeZone}
          onClose={() => setPanel(null)}
          onApproval={showApproval}
        />
      )}
      {panel?.kind === "create" && (
        <QuickCreate
          key={JSON.stringify(panel.initial)}
          initial={panel.initial}
          onClose={() => setPanel(null)}
          onApproval={showApproval}
        />
      )}
      {panel?.kind === "approval" && (
        <ApprovalPanel
          approval={panel.approval}
          onClose={() => setPanel(null)}
          onDecided={() => void refresh()}
        />
      )}
      {finding && (
        <FindTimePanel
          timeZone={timeZone}
          onClose={() => setFinding(false)}
          onPick={(slot, attendees) =>
            create({
              ...fromInstants(
                new Date(slot.start),
                new Date(slot.end),
                timeZone,
              ),
              attendees,
            })
          }
        />
      )}
    </>
  )

  return (
    <div className="min-h-0 min-w-0 flex-1 overflow-y-auto">
      <main className="mx-auto flex max-w-7xl flex-col gap-4 p-4 md:p-6">
        <PageHeader
          title="Calendar"
          description={`Read live from Google Calendar · ${timeZone}`}
          actions={
            <Button
              size="icon-sm"
              variant="ghost"
              aria-label="Keyboard shortcuts"
              onClick={() => setHelp(true)}
            >
              <Keyboard />
            </Button>
          }
        />
        <CalendarToolbar
          title={rangeTitle(view, days, anchor)}
          view={view}
          onView={setView}
          onToday={() => setPicked(null)}
          onStep={step}
          onFindTime={() => setFinding((open) => !open)}
        />
        <UpdatedAt at={dataUpdatedAt} />
        {data?.source === "cache" && (
          <p className="text-xs text-muted-foreground">
            Google could not be reached, so saved events are shown. They may be
            out of date.
          </p>
        )}
        {error && (
          <p className="text-sm text-destructive">{errorText(error)}</p>
        )}
        {move.error && (
          <p className="text-sm text-destructive">{errorText(move.error)}</p>
        )}
        <div className="flex flex-col gap-4 lg:flex-row lg:items-start">
          <div className="min-w-0 flex-1" aria-busy={isPending}>
            {view === "month" ? (
              <MonthGrid
                days={days}
                month={anchor.month}
                events={events}
                timeZone={timeZone}
                now={now}
                onOpen={(event) => setPanel({ kind: "event", event })}
                onCreateOn={(day) =>
                  create(
                    fromWalls(
                      { ...day, hour: 9, minute: 0 },
                      { ...day, hour: 9, minute: 30 },
                    ),
                  )
                }
                onShowDay={(day) =>
                  navigate({ date: dateKey(day), view: "day" }, true)
                }
              />
            ) : (
              <TimeGrid
                days={days}
                events={events}
                timeZone={timeZone}
                now={now}
                onOpen={(event) => setPanel({ kind: "event", event })}
                onCreate={(start, end) => create(fromWalls(start, end))}
                onMove={(event, start, end) =>
                  move.mutate(
                    {
                      id: event.id,
                      change: {
                        start: wallString(wallTime(start, timeZone)),
                        end: wallString(wallTime(end, timeZone)),
                      },
                    },
                    { onSuccess: showApproval },
                  )
                }
              />
            )}
          </div>
          {(panel || finding) && (
            <aside className="flex w-full flex-col gap-3 lg:w-80 lg:shrink-0">
              {side}
            </aside>
          )}
        </div>
        {!panel && !finding && (
          <p className="text-xs text-muted-foreground">
            Click or drag on the grid to add an event. Drag an event to move it.
            Every change waits for your approval.
          </p>
        )}
      </main>
      {help && (
        <ShortcutsHelp
          title="Calendar"
          shortcuts={calendarShortcuts}
          onClose={() => setHelp(false)}
        />
      )}
    </div>
  )
}
