import { useId, useState } from "react"
import { Input } from "@/components/ui/input"
import { groupZones, isZone } from "./zones"

const place = (zone: string) =>
  zone.split("/").slice(1).join(" / ").replaceAll("_", " ") || zone

type Props = {
  value: string
  onChange: (value: string) => void
}

export function TimezoneSelect({ value, onChange }: Props) {
  const [search, setSearch] = useState("")
  const hintId = useId()
  const groups = groupZones(search)
  const shown = groups.some(([, list]) => list.includes(value))
  const valid = isZone(value)

  return (
    <div className="flex flex-col gap-1.5">
      <Input
        type="search"
        aria-label="Search timezones"
        placeholder="Search, e.g. London or Karachi"
        value={search}
        onChange={(event) => setSearch(event.target.value)}
      />
      <select
        aria-label="Timezone"
        aria-invalid={valid ? undefined : true}
        aria-describedby={valid ? undefined : hintId}
        className="h-8 w-full rounded-md border border-input bg-card/60 px-2.5 text-sm outline-none focus-visible:border-ring focus-visible:ring-3 focus-visible:ring-ring/30 aria-invalid:border-destructive dark:bg-input/20"
        value={value}
        onChange={(event) => onChange(event.target.value)}
      >
        {!shown && (
          <option value={value}>{value || "Choose a timezone"}</option>
        )}
        {groups.map(([region, list]) => (
          <optgroup key={region} label={region}>
            {list.map((zone) => (
              <option key={zone} value={zone}>
                {region === "Other" ? zone : place(zone)}
              </option>
            ))}
          </optgroup>
        ))}
      </select>
      {!valid && (
        <p id={hintId} className="text-xs text-destructive">
          Choose a timezone from the list.
        </p>
      )}
    </div>
  )
}
