import { useId } from "react"
import { Input } from "@/components/ui/input"

const zones = Intl.supportedValuesOf("timeZone")

type Props = {
  value: string
  onChange: (value: string) => void
}

export function TimezoneSelect({ value, onChange }: Props) {
  const listId = useId()
  return (
    <>
      <Input
        list={listId}
        value={value}
        onChange={(event) => onChange(event.target.value)}
        placeholder="Europe/London"
        autoComplete="off"
        aria-invalid={
          zones.includes(value) || value === "UTC" ? undefined : true
        }
      />
      <datalist id={listId}>
        {zones.map((zone) => (
          <option key={zone} value={zone} />
        ))}
      </datalist>
    </>
  )
}
