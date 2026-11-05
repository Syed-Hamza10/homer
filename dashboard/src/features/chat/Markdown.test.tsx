import { cleanup, fireEvent, render, screen } from "@testing-library/react"
import { afterEach, describe, expect, it, vi } from "vitest"
import { Markdown } from "./Markdown"

afterEach(cleanup)

describe("Markdown", () => {
  it("renders bold, lists and inline code", () => {
    const { container } = render(
      <Markdown text={"Hello **there**\n\n- one\n- `two`"} />,
    )
    expect(container.querySelector("strong")?.textContent).toBe("there")
    expect(container.querySelectorAll("li")).toHaveLength(2)
    expect(container.querySelector("li code")?.textContent).toBe("two")
  })

  it("opens links in a new tab without an opener", () => {
    render(<Markdown text="See [the docs](https://example.com/docs)." />)
    const link = screen.getByRole("link", { name: "the docs" })
    expect(link.getAttribute("target")).toBe("_blank")
    expect(link.getAttribute("rel")).toContain("noopener")
  })

  it("does not render raw HTML or javascript links", () => {
    const { container } = render(
      <Markdown
        text={'<img src=x onerror="alert(1)">\n\n[x](javascript:alert(1))'}
      />,
    )
    expect(container.querySelector("img")).toBeNull()
    expect(container.querySelector("a")?.getAttribute("href")).toBe("")
  })

  it("copies a code block", async () => {
    const writeText = vi.fn().mockResolvedValue(undefined)
    Object.assign(navigator, { clipboard: { writeText } })
    render(<Markdown text={"```py\nprint('hi')\n```"} />)
    fireEvent.click(screen.getByRole("button", { name: "Copy code" }))
    expect(writeText).toHaveBeenCalledWith("print('hi')")
    expect(await screen.findByRole("button", { name: "Copied" })).toBeTruthy()
  })
})
