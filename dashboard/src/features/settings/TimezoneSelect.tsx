import { useId, useState, type KeyboardEvent } from "react"
import { Input } from "@/components/ui/input"
import { groupZones, isZone } from "./zones"

const place = (zone: string) =>
  zone.split("/").slice(1).join(" / ").replaceAll("_", " ") || zone

const LIST_ROWS = 8

type Props = {
  value: string
  onChange: (value: string) => void
}

export function TimezoneSelect({ value, onChange }: Props) {
  const [search, setSearch] = useState("")
  const hintId = useId()
  const matchId = useId()
  const groups = groupZones(search)
  const matches = groups.flatMap(([, list]) => list)
  const searching = search.trim() !== ""
  const listed = searching && matches.length > 0
  const valid = isZone(value)

  function choose(zone: string) {
    onChange(zone)
    setSearch("")
  }

  function pickFirst(event: KeyboardEvent<HTMLInputElement>) {
    if (event.key !== "Enter") return
    event.preventDefault()
    if (matches.length) choose(matches[0])
  }

  return (
    <div className="flex flex-col gap-1.5">
      <Input
        type="search"
        aria-label="Search timezones"
        aria-describedby={searching ? matchId : undefined}
        placeholder="Search, e.g. London or Karachi"
        value={search}
        onChange={(event) => setSearch(event.target.value)}
        onKeyDown={pickFirst}
      />
      {searching && (
        <p id={matchId} className="text-xs text-muted-foreground">
          {matches.length
            ? `${matches.length} match${matches.length === 1 ? "" : "es"} · Enter picks ${matches[0]}`
            : "No timezone matches that."}
        </p>
      )}
      <select
        aria-label="Timezone"
        aria-invalid={valid ? undefined : true}
        aria-describedby={valid ? undefined : hintId}
        size={
          listed
            ? Math.min(LIST_ROWS, matches.length + groups.length)
            : undefined
        }
        className={`w-full rounded-md border border-input bg-card/60 px-2.5 text-sm outline-none focus-visible:border-ring focus-visible:ring-3 focus-visible:ring-ring/30 aria-invalid:border-destructive dark:bg-input/20 ${listed ? "py-1" : "h-8"}`}
        value={value}
        onChange={(event) => choose(event.target.value)}
      >
        {!matches.includes(value) && !searching && (
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
