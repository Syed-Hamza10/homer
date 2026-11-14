import { useEffect, useRef, useState } from "react"
import { ErrorNotice } from "@/components/ErrorNotice"
import { Button } from "@/components/ui/button"
import { Input } from "@/components/ui/input"
import { FormField } from "@/features/approvals/FormField"
import { holdImeEnter } from "@/lib/ime"
import { clock } from "./format"
import { attendeeList } from "./formValue"
import { PanelFrame } from "./PanelFrame"
import type { Slot } from "./types"
import { useFindTimes } from "./useCalendar"
import { formatIn } from "@/lib/zoned"

type Props = {
  timeZone: string
  onClose: () => void
  onPick: (slot: Slot, attendees: string) => void
}

export const REQUERY_MS = 500

type Ask = { minutes: number; attendees: string[] }

const sameAsk = (a: Ask | undefined, b: Ask): boolean =>
  a !== undefined &&
  a.minutes === b.minutes &&
  a.attendees.join(",") === b.attendees.join(",")

const askable = (ask: Ask): boolean =>
  ask.minutes > 0 && ask.attendees.every((email) => email.includes("@"))

export function FindTimePanel({ timeZone, onClose, onPick }: Props) {
  const [attendees, setAttendees] = useState("")
  const [minutes, setMinutes] = useState(30)
  const [searched, setSearched] = useState(false)
  const timer = useRef<number | undefined>(undefined)
  const find = useFindTimes()
  const ask = { minutes, attendees: attendeeList(attendees) }
  const fresh = sameAsk(find.variables, ask)
  const bad = ask.attendees.find((email) => !email.includes("@"))

  useEffect(() => () => window.clearTimeout(timer.current), [])

  const search = (next: Ask) => {
    window.clearTimeout(timer.current)
    setSearched(true)
    find.mutate(next)
  }

  const change = (nextAttendees: string, nextMinutes: number) => {
    setAttendees(nextAttendees)
    setMinutes(nextMinutes)
    window.clearTimeout(timer.current)
    const next = {
      minutes: nextMinutes,
      attendees: attendeeList(nextAttendees),
    }
    if (searched && askable(next))
      timer.current = window.setTimeout(() => search(next), REQUERY_MS)
  }

  return (
    <PanelFrame eyebrow="Find a time" testId="find-time" onClose={onClose}>
      <form
        className="flex flex-col gap-2"
        onKeyDown={holdImeEnter}
        onSubmit={(event) => {
          event.preventDefault()
          search(ask)
        }}
      >
        <FormField label="Attendees (comma separated)">
          <Input
            value={attendees}
            placeholder="name@example.com"
            onChange={(e) => change(e.target.value, minutes)}
          />
        </FormField>
        <FormField label="Length (minutes)">
          <Input
            type="number"
            min={5}
            max={240}
            step={5}
            value={minutes}
            onChange={(e) => change(attendees, Number(e.target.value))}
            className="w-24"
          />
        </FormField>
        {bad && (
          <p className="text-xs text-destructive">
            Not an email address: {bad}
          </p>
        )}
        <Button
          size="sm"
          type="submit"
          disabled={find.isPending || !minutes || Boolean(bad)}
        >
          Find free times
        </Button>
      </form>
      <ErrorNotice error={find.error} onRetry={() => search(ask)} />
      {find.data && !fresh && (
        <p className="text-xs text-muted-foreground">
          Updating times for the new guests or length…
        </p>
      )}
      {find.data && fresh && find.data.length === 0 && (
        <p className="text-sm text-muted-foreground">
          No common free time in the next two weeks.
        </p>
      )}
      <div className="flex flex-col gap-1.5">
        {find.data?.map((slot) => (
          <Button
            key={slot.start}
            size="sm"
            variant="outline"
            className="justify-start tabular-nums"
            disabled={!fresh}
            onClick={() => onPick(slot, attendees)}
          >
            {formatIn(new Date(slot.start), timeZone, {
              weekday: "short",
              day: "numeric",
              month: "short",
            })}{" "}
            · {clock(slot.start, timeZone)}–{clock(slot.end, timeZone)}
          </Button>
        ))}
      </div>
    </PanelFrame>
  )
}
