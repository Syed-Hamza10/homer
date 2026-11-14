import type { ActivityItem } from "./types"
import { stripUntrusted } from "./untrusted"

export type ToolStep = {
  name: string
  args: Record<string, unknown>
  summary?: string
}

export type StepRow = { text: string; detail: string; failed: boolean }

type Family =
  | "web"
  | "calendar"
  | "mail"
  | "contacts"
  | "draft"
  | "account"
  | "remember"
  | "forget"
  | "other"

const LIVE: Record<Family, string> = {
  web: "Searching the web…",
  calendar: "Checking your calendar…",
  mail: "Looking through your mail…",
  contacts: "Looking up contacts…",
  draft: "Drafting…",
  account: "Checking your account…",
  remember: "Saving to memory…",
  forget: "Forgetting…",
  other: "Working…",
}

const DONE: Record<Family, string> = {
  web: "Searched the web",
  calendar: "Checked your calendar",
  mail: "Looked through your mail",
  contacts: "Looked up contacts",
  draft: "Drafted",
  account: "Checked your account",
  remember: "Saved to memory",
  forget: "Forgot",
  other: "Used a tool",
}

const ROWS: Record<string, [string, string]> = {
  web_search: ["Searching the web", "Searched the web"],
  fetch_page: ["Reading", "Read"],
  cal_list: ["Checking your calendar", "Checked your calendar"],
  cal_find_free_slots: ["Looking for free time", "Looked for free time"],
  cal_create: ["Drafting an event", "Drafted an event"],
  cal_update: ["Drafting an event change", "Drafted an event change"],
  cal_delete: ["Drafting an event deletion", "Drafted an event deletion"],
  mail_search: ["Searching your mail", "Searched your mail"],
  mail_draft: ["Drafting an email", "Drafted an email"],
  mail_profile: ["Checking your account", "Checked your account"],
  contacts_search: ["Looking up contacts", "Looked up contacts"],
  remember: ["Saving to memory", "Saved to memory"],
  forget: ["Forgetting", "Forgot"],
}

const DRAFTS = new Set(["cal_create", "cal_update", "cal_delete", "mail_draft"])
const MONTHS = "Jan Feb Mar Apr May Jun Jul Aug Sep Oct Nov Dec".split(" ")
const DAY_MS = 86_400_000

function family(name: string): Family {
  if (name === "web_search" || name === "fetch_page") return "web"
  if (DRAFTS.has(name)) return "draft"
  if (name.startsWith("cal_")) return "calendar"
  if (name === "mail_profile") return "account"
  if (name.startsWith("mail_")) return "mail"
  if (name.startsWith("contacts_")) return "contacts"
  if (name === "remember" || name === "forget") return name
  return "other"
}

function plural(count: number, noun: string): string {
  return `${count} ${noun}${count === 1 ? "" : "s"}`
}

function text(value: unknown): string {
  return typeof value === "string" ? stripUntrusted(value).trim() : ""
}

function domain(url: unknown): string {
  try {
    return new URL(String(url)).hostname.replace(/^www\./, "")
  } catch {
    return text(url)
  }
}

function pageTitle(summary: string | undefined): string {
  const match = summary && /"title":\s*"((?:[^"\\]|\\.)*)"/.exec(summary)
  if (!match) return ""
  try {
    return text(JSON.parse(`"${match[1]}"`))
  } catch {
    return ""
  }
}

function isoDay(value: unknown): Date | null {
  const match =
    typeof value === "string" && /^(\d{4})-(\d{2})-(\d{2})/.exec(value)
  if (!match) return null
  return new Date(Date.UTC(+match[1], +match[2] - 1, +match[3]))
}

function shortDay(day: Date): string {
  return `${MONTHS[day.getUTCMonth()]} ${day.getUTCDate()}`
}

function dateRange(start: unknown, end: unknown): string {
  const first = isoDay(start)
  if (!first) return ""
  const after = isoDay(end)
  const last = after && new Date(after.getTime() - DAY_MS)
  return last && last > first
    ? `${shortDay(first)} – ${shortDay(last)}`
    : shortDay(first)
}

function failed(step: ToolStep): boolean {
  return step.summary !== undefined && /^\s*\{\s*"error"/.test(step.summary)
}

function service(step: ToolStep): string {
  if (step.name === "fetch_page") return domain(step.args.url) || "the page"
  if (step.name === "web_search") return "the search engine"
  if (step.name.startsWith("cal_")) return "Google Calendar"
  if (step.name.startsWith("mail_") || step.name.startsWith("contacts_"))
    return "Gmail"
  return "the service"
}

function detail({ name, args, summary }: ToolStep): string {
  if (name === "fetch_page") {
    const title = pageTitle(summary)
    const host = domain(args.url)
    return title && title !== host ? `${title} · ${host}` : host
  }
  if (name.startsWith("cal_"))
    return text(args.summary) || dateRange(args.start ?? args.date, args.end)
  if (name === "mail_draft") return text(args.to) && `to ${text(args.to)}`
  return text(args.query) || text(args.text)
}

export function pairSteps(items: ActivityItem[]): ToolStep[] {
  const steps: ToolStep[] = []
  for (const item of items) {
    if (item.kind === "tool_call")
      steps.push({ name: item.name, args: item.args ?? {} })
    if (item.kind !== "tool_result") continue
    const open = steps.find(
      (step) => step.name === item.name && step.summary === undefined,
    )
    if (open) open.summary = item.summary
  }
  return steps
}

export function stepRow(step: ToolStep, running: boolean): StepRow {
  if (failed(step))
    return { text: `Couldn't reach ${service(step)}`, detail: "", failed: true }
  const words = step.name.replaceAll("_", " ")
  const [live, done] = ROWS[step.name] ?? [`Using ${words}`, `Used ${words}`]
  return {
    text: step.summary !== undefined ? done : running ? live : "Skipped",
    detail: detail(step),
    failed: false,
  }
}

export function headline(
  steps: ToolStep[],
  live: { running: boolean; status: string | null; sources: number },
): string {
  if (live.running) {
    if (live.status) return live.status
    const current =
      steps.findLast((step) => step.summary === undefined) ?? steps.at(-1)
    if (!current) return "Thinking…"
    if (current.name === "fetch_page") {
      const pages = steps.filter((step) => step.name === "fetch_page").length
      return `Reading ${plural(pages, "page")}…`
    }
    return LIVE[family(current.name)]
  }
  const labels = [...new Set(steps.map((step) => family(step.name)))].map(
    (kind) =>
      kind === "web" && live.sources > 0
        ? `${DONE.web} · ${plural(live.sources, "source")}`
        : DONE[kind],
  )
  return labels.join(" · ")
}
