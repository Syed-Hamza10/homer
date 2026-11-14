import { ErrorNotice } from "@/components/ErrorNotice"
import { useState } from "react"
import { Video } from "lucide-react"
import { Button } from "@/components/ui/button"
import type { Approval } from "@/features/approvals/types"
import { EventForm } from "./EventForm"
import { responseText, whenText } from "./format"
import { endOf, fromEvent, startOf, toFields } from "./formValue"
import { PanelFrame } from "./PanelFrame"
import type { CalendarEvent, EventFields } from "./types"
import { useCancelEvent, useUpdateEvent } from "./useCalendar"

type Props = {
  event: CalendarEvent
  timeZone: string
  onClose: () => void
  onApproval: (approval: Approval) => void
}

type Mode = "view" | "edit" | "move"

export function EventPopover({ event, timeZone, onClose, onApproval }: Props) {
  const [mode, setMode] = useState<Mode>("view")
  const [value, setValue] = useState(() => fromEvent(event, timeZone))
  const update = useUpdateEvent()
  const cancel = useCancelEvent()
  const busy = update.isPending || cancel.isPending
  const error = update.error ?? cancel.error
  const send = (change: Partial<EventFields>) =>
    update.mutate({ id: event.id, change }, { onSuccess: onApproval })
  const back = () => {
    setValue(fromEvent(event, timeZone))
    setMode("view")
  }

  if (mode === "edit") {
    const fields = toFields(value)
    const { start, end, ...details } = fields
    return (
      <PanelFrame eyebrow="Edit event" testId="event-popover" onClose={onClose}>
        <EventForm
          value={value}
          onChange={setValue}
          onBack={back}
          submitLabel="Ask to save"
          busy={busy}
          error={error}
          withTime={!event.all_day}
          onSubmit={() =>
            send(event.all_day ? details : { ...details, start, end })
          }
        />
      </PanelFrame>
    )
  }

  if (mode === "move") {
    return (
      <PanelFrame eyebrow="Move event" testId="event-popover" onClose={onClose}>
        <EventForm
          value={value}
          onChange={setValue}
          onBack={back}
          submitLabel="Ask to move"
          busy={busy}
          error={error}
          withDetails={false}
          onSubmit={() => send({ start: startOf(value), end: endOf(value) })}
        />
      </PanelFrame>
    )
  }

  return (
    <PanelFrame eyebrow="Event" testId="event-popover" onClose={onClose}>
      <div className="flex flex-col gap-1">
        <h2 className="font-heading text-xl leading-tight">
          {event.title || "(no title)"}
        </h2>
        <p className="text-sm text-muted-foreground tabular-nums">
          {whenText(event, timeZone)}
        </p>
        {event.location && <p className="text-sm">{event.location}</p>}
        {event.video_link && (
          <a
            href={event.video_link}
            target="_blank"
            rel="noopener noreferrer"
            className="inline-flex items-center gap-1.5 text-sm text-primary underline-offset-4 hover:underline"
          >
            <Video className="size-3.5" />
            Join video call
          </a>
        )}
      </div>
      {event.people.length > 0 && (
        <ul className="flex flex-col gap-1 text-sm">
          {event.people.map((person) => (
            <li key={person.email} className="flex justify-between gap-3">
              <span className="truncate">
                {person.name || person.email}
                {person.organizer && (
                  <span className="text-muted-foreground"> · organizer</span>
                )}
              </span>
              <span className="shrink-0 text-xs text-muted-foreground">
                {responseText(person.response)}
              </span>
            </li>
          ))}
        </ul>
      )}
      {event.description && (
        <p className="text-sm leading-relaxed whitespace-pre-wrap text-muted-foreground">
          {event.description}
        </p>
      )}
      <div className="flex flex-wrap gap-2">
        <Button
          size="sm"
          variant="outline"
          disabled={busy}
          onClick={() => setMode("edit")}
        >
          Edit
        </Button>
        {!event.all_day && (
          <Button
            size="sm"
            variant="outline"
            disabled={busy}
            onClick={() => setMode("move")}
          >
            Move
          </Button>
        )}
        <Button
          size="sm"
          variant="destructive"
          disabled={busy}
          onClick={() => cancel.mutate(event.id, { onSuccess: onApproval })}
        >
          Cancel event
        </Button>
      </div>
      <ErrorNotice error={error} className="text-xs" />
    </PanelFrame>
  )
}
