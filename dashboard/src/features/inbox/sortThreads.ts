import { displayName } from "./format"
import type { ThreadSummary } from "./types"

export type SortColumn = "from" | "subject" | "date"
export type SortDirection = "asc" | "desc"
export type ThreadSort = {
  column: SortColumn
  direction: SortDirection
  unreadFirst: boolean
}

export const defaultSort: ThreadSort = {
  column: "date",
  direction: "desc",
  unreadFirst: false,
}

const collator = new Intl.Collator(undefined, {
  sensitivity: "base",
  numeric: true,
})

function compareBy(
  column: SortColumn,
  sentView: boolean,
): (a: ThreadSummary, b: ThreadSummary) => number {
  if (column === "date")
    return (a, b) =>
      Date.parse(a.received_at ?? "0") - Date.parse(b.received_at ?? "0")
  if (column === "subject")
    return (a, b) => collator.compare(a.subject, b.subject)
  const who = (thread: ThreadSummary) =>
    displayName(sentView ? thread.to : thread.sender)
  return (a, b) => collator.compare(who(a), who(b))
}

export function sortThreads(
  rows: ThreadSummary[],
  sort: ThreadSort,
  sentView: boolean,
): ThreadSummary[] {
  const sign = sort.direction === "asc" ? 1 : -1
  const compare = compareBy(sort.column, sentView)
  const unread = (a: ThreadSummary, b: ThreadSummary) =>
    sort.unreadFirst ? Number(b.unread) - Number(a.unread) : 0
  return [...rows].sort((a, b) => unread(a, b) || sign * compare(a, b))
}

export function nextSort(sort: ThreadSort, column: SortColumn): ThreadSort {
  if (sort.column === column)
    return { ...sort, direction: sort.direction === "asc" ? "desc" : "asc" }
  return { ...sort, column, direction: column === "date" ? "desc" : "asc" }
}

export function directionText(column: SortColumn, direction: SortDirection) {
  if (column === "date")
    return direction === "desc" ? "newest first" : "oldest first"
  return direction === "asc" ? "A to Z" : "Z to A"
}
