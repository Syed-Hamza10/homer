import { describe, expect, it } from "vitest"
import { headline, pairSteps, stepRow, type ToolStep } from "./activity"
import type { ActivityItem } from "./types"

const search: ToolStep = {
  name: "web_search",
  args: { query: "<untrusted>who won</untrusted>", max_results: 8 },
  summary: '{"results": [{"title": "<untrusted>Story</untrusted>"',
}

const page = (url: string, summary?: string): ToolStep => ({
  name: "fetch_page",
  args: { url },
  summary,
})

const idle = { running: false, status: null, sources: 0 }
const busy = { running: true, status: null, sources: 0 }

describe("pairSteps", () => {
  it("matches each result to the oldest open call of the same tool", () => {
    const items: ActivityItem[] = [
      {
        kind: "tool_call",
        name: "fetch_page",
        args: { url: "https://a.test" },
      },
      {
        kind: "tool_call",
        name: "fetch_page",
        args: { url: "https://b.test" },
      },
      { kind: "tool_result", name: "fetch_page", summary: "{}" },
      { kind: "reconnect", url: "/settings" },
    ]
    expect(pairSteps(items)).toEqual([
      page("https://a.test", "{}"),
      page("https://b.test"),
    ])
  })
})

describe("headline", () => {
  it("maps each tool to a live label", () => {
    const live = (name: string) => headline([{ name, args: {} }], busy)
    expect(live("web_search")).toBe("Searching the web…")
    expect(live("cal_list")).toBe("Checking your calendar…")
    expect(live("mail_search")).toBe("Looking through your mail…")
    expect(live("mail_draft")).toBe("Drafting…")
    expect(live("cal_create")).toBe("Drafting…")
    expect(live("contacts_search")).toBe("Looking up contacts…")
    expect(live("remember")).toBe("Saving to memory…")
    expect(live("forget")).toBe("Forgetting…")
  })

  it("counts the pages being read", () => {
    const steps = [search, page("https://a.test"), page("https://b.test")]
    expect(headline(steps, busy)).toBe("Reading 2 pages…")
  })

  it("prefers the status event while running", () => {
    expect(headline([search], { ...busy, status: "Writing the answer…" })).toBe(
      "Writing the answer…",
    )
  })

  it("sums up a finished turn with its sources", () => {
    const steps = [search, page("https://a.test", "{}")]
    expect(headline(steps, { ...idle, sources: 2 })).toBe(
      "Searched the web · 2 sources",
    )
    expect(headline(steps, idle)).toBe("Searched the web")
    const both = [{ name: "cal_list", args: {}, summary: "{}" }, search]
    expect(headline(both, { ...idle, sources: 1 })).toBe(
      "Checked your calendar · Searched the web · 1 source",
    )
  })
})

describe("stepRow", () => {
  it("shows the query without untrusted tags", () => {
    expect(stepRow(search, false)).toEqual({
      text: "Searched the web",
      detail: "who won",
      failed: false,
    })
  })

  it("shows the page title and domain, never the page text", () => {
    const row = stepRow(
      page(
        "https://www.example.test/story",
        '{"title": "<untrusted>Big \\"news\\"</untrusted>", "text": "<untrusted>Secret body',
      ),
      false,
    )
    expect(row.detail).toBe('Big "news" · example.test')
    expect(JSON.stringify(row)).not.toContain("Secret")
  })

  it("falls back to the domain while a page is still loading", () => {
    expect(stepRow(page("https://example.test/a"), true)).toEqual({
      text: "Reading",
      detail: "example.test",
      failed: false,
    })
  })

  it("shows the calendar range", () => {
    const row = stepRow(
      {
        name: "cal_list",
        args: {
          start: "2026-11-14T00:00:00+00:00",
          end: "2026-11-17T00:00:00+00:00",
        },
        summary: "{}",
      },
      false,
    )
    expect(row.detail).toBe("Nov 14 – Nov 16")
    const day = stepRow(
      {
        name: "cal_list",
        args: {
          start: "2026-11-14T00:00:00+00:00",
          end: "2026-11-15T00:00:00+00:00",
        },
        summary: "{}",
      },
      false,
    )
    expect(day.detail).toBe("Nov 14")
  })

  it("marks a page the turn never needed as skipped", () => {
    expect(stepRow(page("https://example.test/a"), false).text).toBe("Skipped")
  })

  it("turns a failed call into plain words", () => {
    const failed = page("https://www.bbc.com/news", '{"error": "timeout"}')
    expect(stepRow(failed, false)).toEqual({
      text: "Couldn't reach bbc.com",
      detail: "",
      failed: true,
    })
    expect(
      stepRow({ name: "cal_list", args: {}, summary: '{"error": "x"}' }, false)
        .text,
    ).toBe("Couldn't reach Google Calendar")
  })
})
