export function untilLabel(start: string, end: string, now: number): string {
  const opens = new Date(start).getTime()
  if (now >= opens) return now < new Date(end).getTime() ? "now" : ""
  const minutes = Math.ceil((opens - now) / 60000)
  if (minutes < 60) return `in ${minutes} min`
  const hours = Math.floor(minutes / 60)
  const rest = minutes % 60
  return rest ? `in ${hours} h ${rest} min` : `in ${hours} h`
}

export function personName(address: string): string {
  const name = address.split("<")[0].trim().replace(/^"|"$/g, "")
  return name || address.replace(/[<>]/g, "").trim()
}

export function attendeeLine(attendees: string[]): string {
  const names = attendees.map(personName)
  if (names.length <= 3) return names.join(", ")
  return `${names.slice(0, 3).join(", ")} +${names.length - 3}`
}

export function clockTime(value: string): string {
  return new Date(value).toLocaleTimeString([], {
    hour: "2-digit",
    minute: "2-digit",
    hourCycle: "h23",
  })
}

export function plural(count: number, word: string): string {
  return `${count} ${word}${count === 1 ? "" : "s"}`
}
