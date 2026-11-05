import { useState } from "react"
import { Button } from "@/components/ui/button"
import { Input } from "@/components/ui/input"
import { FormField } from "@/features/approvals/FormField"
import { errorText } from "@/lib/errorText"
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

export function FindTimePanel({ timeZone, onClose, onPick }: Props) {
  const [attendees, setAttendees] = useState("")
  const [minutes, setMinutes] = useState(30)
  const find = useFindTimes()
  const bad = attendeeList(attendees).find((email) => !email.includes("@"))

  return (
    <PanelFrame eyebrow="Find a time" testId="find-time" onClose={onClose}>
      <form
        className="flex flex-col gap-2"
        onSubmit={(event) => {
          event.preventDefault()
          find.mutate({ minutes, attendees: attendeeList(attendees) })
        }}
      >
        <FormField label="Attendees (comma separated)">
          <Input
            value={attendees}
            placeholder="name@example.com"
            onChange={(e) => setAttendees(e.target.value)}
          />
        </FormField>
        <FormField label="Length (minutes)">
          <Input
            type="number"
            min={5}
            max={240}
            step={5}
            value={minutes}
            onChange={(e) => setMinutes(Number(e.target.value))}
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
      {find.error && (
        <p className="text-xs text-destructive">{errorText(find.error)}</p>
      )}
      {find.data && find.data.length === 0 && (
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
