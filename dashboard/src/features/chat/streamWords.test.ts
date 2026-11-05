import { describe, expect, it } from "vitest"
import { rehypeStreamWords } from "./streamWords"

describe("rehypeStreamWords", () => {
  it("wraps each word in a fading span and keeps code as is", () => {
    const tree = {
      type: "root",
      children: [
        {
          type: "element",
          tagName: "p",
          properties: {},
          children: [{ type: "text", value: "Hi there" }],
        },
        {
          type: "element",
          tagName: "pre",
          properties: {},
          children: [{ type: "text", value: "a b" }],
        },
      ],
    }
    rehypeStreamWords()(tree)
    const [p, pre] = tree.children
    expect(p.children.map((c) => c.type)).toEqual([
      "element",
      "text",
      "element",
    ])
    expect(pre.children).toEqual([{ type: "text", value: "a b" }])
  })
})
