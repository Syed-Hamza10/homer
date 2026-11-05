type Text = { type: "text"; value: string }
type Element = {
  type: "element"
  tagName: string
  properties: Record<string, unknown>
  children: Child[]
}
type Child = Text | Element | { type: string; children?: Child[] }
type Parent = { children?: Child[] }

const SKIP = new Set(["code", "pre"])

function words(text: Text): Child[] {
  return text.value
    .split(/(\s+)/)
    .filter(Boolean)
    .map((part) =>
      /^\s+$/.test(part)
        ? { type: "text", value: part }
        : {
            type: "element",
            tagName: "span",
            properties: { className: ["stream-word"] },
            children: [{ type: "text", value: part }],
          },
    )
}

function wrap(node: Parent): void {
  if (!node.children) return
  node.children = node.children.flatMap((child) => {
    if (child.type === "text") return words(child as Text)
    if (child.type === "element" && SKIP.has((child as Element).tagName))
      return [child]
    wrap(child as Parent)
    return [child]
  })
}

export function rehypeStreamWords() {
  return (tree: Parent) => wrap(tree)
}
