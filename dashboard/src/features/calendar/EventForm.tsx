import { Button } from "@/components/ui/button"
import { Input } from "@/components/ui/input"
import { Textarea } from "@/components/ui/textarea"
import { FormField } from "@/features/approvals/FormField"
import { holdImeEnter } from "@/lib/ime"
import { problem, withStartDate } from "./formValue"
import type { FormValue } from "./types"

type Props = {
  value: FormValue
  onChange: (value: FormValue) => void
  onSubmit: () => void
  onBack: () => void
  submitLabel: string
  busy: boolean
  error: string | null
  withTime?: boolean
  withDetails?: boolean
}

export function EventForm({
  value,
  onChange,
  onSubmit,
  onBack,
  submitLabel,
  busy,
  error,
  withTime = true,
  withDetails = true,
}: Props) {
  const invalid = problem(value, withTime)
  const set = (key: keyof FormValue) => (text: string) =>
    onChange({ ...value, [key]: text })

  return (
    <form
      className="flex flex-col gap-2"
      onKeyDown={holdImeEnter}
      onSubmit={(event) => {
        event.preventDefault()
        if (!invalid) onSubmit()
      }}
    >
      {withDetails && (
        <FormField label="Title">
          <Input
            value={value.title}
            required
            onChange={(e) => set("title")(e.target.value)}
          />
        </FormField>
      )}
      {withTime && (
        <div className="grid grid-cols-[1fr_auto] gap-2">
          <FormField label="Start date">
            <Input
              type="date"
              value={value.startDate}
              onChange={(e) => onChange(withStartDate(value, e.target.value))}
            />
          </FormField>
          <FormField label="Start time">
            <Input
              type="time"
              step={900}
              value={value.start}
              onChange={(e) => set("start")(e.target.value)}
            />
          </FormField>
          <FormField label="End date">
            <Input
              type="date"
              value={value.endDate}
              min={value.startDate}
              onChange={(e) => set("endDate")(e.target.value)}
            />
          </FormField>
          <FormField label="End time">
            <Input
              type="time"
              step={900}
              value={value.end}
              onChange={(e) => set("end")(e.target.value)}
            />
          </FormField>
        </div>
      )}
      {withDetails && (
        <>
          <FormField label="Attendees (comma separated)">
            <Input
              value={value.attendees}
              placeholder="name@example.com"
              onChange={(e) => set("attendees")(e.target.value)}
            />
          </FormField>
          <FormField label="Location">
            <Input
              value={value.location}
              onChange={(e) => set("location")(e.target.value)}
            />
          </FormField>
          <FormField label="Description">
            <Textarea
              value={value.description}
              onChange={(e) => set("description")(e.target.value)}
            />
          </FormField>
        </>
      )}
      {(invalid || error) && (
        <p className="text-xs text-destructive">{invalid ?? error}</p>
      )}
      <div className="flex gap-2">
        <Button size="sm" type="submit" disabled={busy || Boolean(invalid)}>
          {submitLabel}
        </Button>
        <Button size="sm" type="button" variant="outline" onClick={onBack}>
          Back
        </Button>
      </div>
    </form>
  )
}
