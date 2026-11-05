import { describe, expect, it } from "vitest"
import { splitSources } from "./sources"

describe("splitSources", () => {
  it("takes the search job's Sources block off the body", () => {
    const text =
      "AI moved fast this week.\n\nSources:\n- Big news: https://www.example.com/a\n- https://news.example.org/b"
    expect(splitSources(text)).toEqual({
      body: "AI moved fast this week.",
      sources: [
        {
          url: "https://www.example.com/a",
          title: "Big news",
          domain: "example.com",
        },
        {
          url: "https://news.example.org/b",
          title: "news.example.org",
          domain: "news.example.org",
        },
      ],
    })
  })

  it("reads markdown links under a bold header", () => {
    const text =
      "Answer.\n\n**Sources**\n- [Docs page](https://docs.example.com/x)"
    expect(splitSources(text).sources).toEqual([
      {
        url: "https://docs.example.com/x",
        title: "Docs page",
        domain: "docs.example.com",
      },
    ])
    expect(splitSources(text).body).toBe("Answer.")
  })

  it("leaves text without a Sources block alone", () => {
    const text = "Just an answer with https://example.com inside."
    expect(splitSources(text)).toEqual({ body: text, sources: [] })
  })

  it("leaves a Sources block with prose after it alone", () => {
    const text = "Sources:\n- https://example.com\nThat is all I found."
    expect(splitSources(text).sources).toEqual([])
  })

  it("refuses non-http links", () => {
    const text = "Hi\nSources:\n- [x](javascript:alert(1))"
    expect(splitSources(text).sources).toEqual([])
  })
})
