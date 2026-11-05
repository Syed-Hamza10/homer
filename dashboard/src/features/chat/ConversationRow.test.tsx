import { cleanup, fireEvent, render, screen } from "@testing-library/react"
import { afterEach, describe, expect, it, vi } from "vitest"
import { ConversationRow } from "./ConversationRow"

afterEach(cleanup)

const conversation = { id: "1", title: "Trip", updated_at: "" }

function setup() {
  const onRename = vi.fn()
  const onDelete = vi.fn()
  render(
    <ConversationRow
      conversation={conversation}
      selected={false}
      onSelect={vi.fn()}
      onRename={onRename}
      onDelete={onDelete}
    />,
  )
  return { onRename, onDelete }
}

describe("ConversationRow", () => {
  it("renames inline on Enter", () => {
    const { onRename } = setup()
    fireEvent.click(screen.getByRole("button", { name: "Rename" }))
    const input = screen.getByRole("textbox", { name: "Conversation title" })
    fireEvent.change(input, { target: { value: "Trip to Lahore" } })
    fireEvent.keyDown(input, { key: "Enter" })
    expect(onRename).toHaveBeenCalledWith("Trip to Lahore")
  })

  it("deletes only after confirming", () => {
    const { onDelete } = setup()
    fireEvent.click(screen.getByRole("button", { name: "Delete" }))
    fireEvent.click(screen.getByRole("button", { name: "Cancel delete" }))
    expect(onDelete).not.toHaveBeenCalled()
    fireEvent.click(screen.getByRole("button", { name: "Delete" }))
    fireEvent.click(screen.getByRole("button", { name: "Confirm delete" }))
    expect(onDelete).toHaveBeenCalledOnce()
  })
})
