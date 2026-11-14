const zones = [...new Set([...Intl.supportedValuesOf("timeZone"), "UTC"])]

export function isZone(value: string): boolean {
  return zones.includes(value)
}

export function groupZones(search: string): [string, string[]][] {
  const needle = search.trim().toLowerCase().replace(/\s+/g, "_")
  const groups = new Map<string, string[]>()
  for (const zone of zones) {
    if (needle && !zone.toLowerCase().includes(needle)) continue
    const region = zone.includes("/") ? zone.split("/")[0] : "Other"
    groups.set(region, [...(groups.get(region) ?? []), zone])
  }
  return [...groups.entries()].sort(([a], [b]) => a.localeCompare(b))
}
