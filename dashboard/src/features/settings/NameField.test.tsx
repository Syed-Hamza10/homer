import { cleanup, fireEvent, render, screen } from "@testing-library/react"
import { afterEach, describe, expect, it, vi } from "vitest"
import { NameField } from "./NameField"

afterEach(cleanup)

describe("name field", () => {
  it("nudges for a name while neither name nor signature is set", () => {
    render(<NameField value="" signature="" onChange={vi.fn()} />)
    expect(screen.getByText("Add your name so emails are signed.")).toBeTruthy()
  })

  it("hides the nudge once a name is given and reports changes", () => {
    const onChange = vi.fn()
    render(<NameField value="Jordan" signature="" onChange={onChange} />)
    expect(screen.queryByText("Add your name so emails are signed.")).toBeNull()
    fireEvent.change(screen.getByLabelText("Your name"), {
      target: { value: "Jo" },
    })
    expect(onChange).toHaveBeenCalledWith("Jo")
  })
})
