import { describe, expect, it } from "vitest"
import { stripUntrusted } from "./untrusted"

describe("stripUntrusted", () => {
  it("removes the tags and keeps the text", () => {
    expect(stripUntrusted("<untrusted>A</untrusted> and <UNTRUSTED>B")).toBe(
      "A and B",
    )
  })
})
