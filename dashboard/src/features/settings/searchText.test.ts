import { describe, expect, it } from "vitest"
import { privacyLine, probeText } from "./searchText"

describe("search privacy line", () => {
  it("names DuckDuckGo when there is no key", () => {
    expect(privacyLine("brave", "brave", false, true)).toBe(
      "Your search question goes to DuckDuckGo. Emails and documents never do.",
    )
  })

  it("names the keyed service when it is the main one", () => {
    expect(privacyLine("tavily", "brave", true, true)).toBe(
      "Your search question goes to Tavily. Emails and documents never do.",
    )
  })

  it("names both when the key is a backup", () => {
    expect(privacyLine("duckduckgo", "brave", true, true)).toContain(
      "DuckDuckGo (or Brave Search when it blocks)",
    )
    expect(privacyLine("duckduckgo", "brave", true, false)).toContain(
      "goes to DuckDuckGo.",
    )
  })
})

describe("search test result", () => {
  it("explains each outcome plainly", () => {
    expect(probeText({ status: "ok", provider: "brave", results: 3 })).toBe(
      "Works: Brave Search answered with 3 results.",
    )
    expect(
      probeText({ status: "invalid_key", provider: "tavily", results: 0 }),
    ).toBe("Tavily did not accept the key.")
    expect(
      probeText({ status: "blocked", provider: "duckduckgo", results: 0 }),
    ).toContain("DuckDuckGo is blocking")
  })
})
