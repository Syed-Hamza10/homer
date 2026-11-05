import { describe, expect, it } from "vitest"
import { emailDocument, safeEmailHtml } from "./emailDocument"

const HOSTILE =
  '<p onclick="steal()">Hi</p><script>alert(1)</script>' +
  '<img src="https://tracker.example.test/p.gif" onerror="alert(2)">' +
  '<a href="javascript:alert(3)">Deck</a> <a href="https://example.test">site</a>' +
  "<style>body{background:url(https://e.example.test)}</style>" +
  '<form action="https://e.example.test"><input name="q"></form>'

describe("safeEmailHtml", () => {
  it("drops scripts, handlers, styles, forms and javascript links", () => {
    const html = safeEmailHtml(HOSTILE, false)
    for (const unsafe of [
      "<script",
      "onclick",
      "onerror",
      "javascript:",
      "<style",
      "<form",
      "<input",
    ])
      expect(html).not.toContain(unsafe)
    expect(html).toContain("Hi")
    expect(html).toContain(
      '<a href="https://example.test" target="_blank" rel="noopener noreferrer nofollow">site</a>',
    )
  })

  it("blocks remote images until they are shown", () => {
    expect(safeEmailHtml(HOSTILE, false)).not.toContain("tracker.example.test")
    expect(safeEmailHtml(HOSTILE, true)).toContain(
      'src="https://tracker.example.test/p.gif"',
    )
  })

  it("keeps inline images", () => {
    expect(safeEmailHtml('<img src="data:image/png;base64,AA">', false)).toBe(
      '<img src="data:image/png;base64,AA">',
    )
  })
})

describe("emailDocument", () => {
  it("locks the frame down with a content security policy", () => {
    const blocked = emailDocument("<p>x</p>", false)
    expect(blocked).toContain("default-src 'none'; img-src data:;")
    expect(blocked).toContain('<base target="_blank">')
    expect(emailDocument("<p>x</p>", true)).toContain("img-src data: https:;")
  })
})
