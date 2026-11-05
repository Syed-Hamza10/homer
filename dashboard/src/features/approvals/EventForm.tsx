import { Input } from "@/components/ui/input"
import { FormField } from "./FormField"
import type { EventEdit } from "./types"

type Props = { value: EventEdit; onChange: (value: EventEdit) => void }

export function EventForm({ value, onChange }: Props) {
  return (
    <>
      <FormField label="Title">
        <Input
          value={value.title}
          onChange={(e) => onChange({ ...value, title: e.target.value })}
        />
      </FormField>
      <div className="grid grid-cols-3 gap-2">
        <FormField label="Date">
          <Input
            type="date"
            value={value.date}
            onChange={(e) => onChange({ ...value, date: e.target.value })}
          />
        </FormField>
        <FormField label="Start">
          <Input
            type="time"
            value={value.start}
            onChange={(e) => onChange({ ...value, start: e.target.value })}
          />
        </FormField>
        <FormField label="End">
          <Input
            type="time"
            value={value.end}
            onChange={(e) => onChange({ ...value, end: e.target.value })}
          />
        </FormField>
      </div>
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
    </>
  )
}
