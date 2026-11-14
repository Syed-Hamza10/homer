import { Input } from "@/components/ui/input"
import { followedEndDate } from "./editable"
import { FormField } from "./FormField"
import type { EventEdit } from "./types"

type Props = {
  value: EventEdit
  onChange: (value: EventEdit) => void
  guests?: boolean
}

export function EventForm({ value, onChange, guests = true }: Props) {
  return (
    <>
      <FormField label="Title">
        <Input
          value={value.title}
          onChange={(e) => onChange({ ...value, title: e.target.value })}
        />
      </FormField>
      <div className="grid grid-cols-[1fr_auto] gap-2">
        <FormField label="Start date">
          <Input
            type="date"
            value={value.date}
            onChange={(e) =>
              onChange({
                ...value,
                date: e.target.value,
                end_date: followedEndDate(
                  value.date,
                  value.end_date,
                  e.target.value,
                ),
              })
            }
          />
        </FormField>
        <FormField label="Start time">
          <Input
            type="time"
            value={value.start}
            onChange={(e) => onChange({ ...value, start: e.target.value })}
          />
        </FormField>
        <FormField label="End date">
          <Input
            type="date"
            value={value.end_date}
            min={value.date}
            onChange={(e) => onChange({ ...value, end_date: e.target.value })}
          />
        </FormField>
        <FormField label="End time">
          <Input
            type="time"
            value={value.end}
            onChange={(e) => onChange({ ...value, end: e.target.value })}
          />
        </FormField>
      </div>
      {guests && (
        <FormField label="Attendees (comma separated)">
          <Input
            value={value.attendees.join(", ")}
            onChange={(e) =>
              onChange({
                ...value,
                attendees: e.target.value
                  .split(",")
                  .map((a) => a.trim())
                  .filter(Boolean),
              })
            }
          />
        </FormField>
      )}
    </>
  )
}
