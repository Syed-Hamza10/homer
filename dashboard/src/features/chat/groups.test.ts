import { describe, expect, it } from "vitest"
import { filterConversations, groupConversations } from "./groups"
import type { Conversation } from "./types"

const now = new Date(2026, 10, 6, 15, 0)
const at = (id: string, title: string, date: Date): Conversation => ({
  id,
  title,
  updated_at: date.toISOString(),
})

const list = [
  at("1", "Morning plan", new Date(2026, 10, 6, 0, 5)),
  at("2", "Late call", new Date(2026, 10, 5, 23, 50)),
  at("3", "Trip", new Date(2026, 10, 1, 12, 0)),
  at("4", "Invoice", new Date(2026, 9, 1, 12, 0)),
]

describe("groupConversations", () => {
  it("buckets by local day and drops empty groups", () => {
    const groups = groupConversations(list, now)
    expect(groups.map((g) => [g.label, g.items.map((c) => c.id)])).toEqual([
      ["Today", ["1"]],
      ["Yesterday", ["2"]],
      ["Previous 7 days", ["3"]],
      ["Older", ["4"]],
    ])
  })

  it("returns nothing for no conversations", () => {
    expect(groupConversations([], now)).toEqual([])
  })
})

describe("filterConversations", () => {
  it("matches titles case-insensitively", () => {
    expect(filterConversations(list, "  tri ").map((c) => c.id)).toEqual(["3"])
  })

  it("keeps everything for an empty query", () => {
    expect(filterConversations(list, " ")).toHaveLength(4)
  })
})
