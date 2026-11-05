export type Source = { url: string; title: string; domain: string }
export type SplitAnswer = { body: string; sources: Source[] }

const HEADER = /^\s*(?:#+\s*)?(?:\*\*)?sources:?(?:\*\*)?:?\s*$/i
const ITEM = /^\s*[-*]\s+(?:\[([^\]]+)\]\((\S+?)\)|(?:(.+?):\s+)?(\S+))\s*$/

function toSource(title: string | undefined, url: string): Source | null {
  try {
    const parsed = new URL(url)
    if (parsed.protocol !== "http:" && parsed.protocol !== "https:") return null
    const domain = parsed.hostname.replace(/^www\./, "")
    return { url, title: title?.trim() || domain, domain }
  } catch {
    return null
  }
}

export function splitSources(text: string): SplitAnswer {
  const lines = text.split("\n")
  const header = lines.findLastIndex((line) => HEADER.test(line))
  if (header < 0) return { body: text, sources: [] }
  const sources: Source[] = []
  for (const line of lines.slice(header + 1)) {
    if (!line.trim()) continue
    const match = ITEM.exec(line)
    const source = match && toSource(match[1] ?? match[3], match[2] ?? match[4])
    if (!source) return { body: text, sources: [] }
    sources.push(source)
  }
  if (!sources.length) return { body: text, sources: [] }
  return { body: lines.slice(0, header).join("\n").trimEnd(), sources }
}
