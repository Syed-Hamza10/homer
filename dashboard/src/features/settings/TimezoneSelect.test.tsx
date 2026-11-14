import { cleanup, fireEvent, render, screen } from "@testing-library/react"
import { afterEach, describe, expect, it, vi } from "vitest"
import { TimezoneSelect } from "./TimezoneSelect"
import { groupZones } from "./zones"

afterEach(cleanup)

describe("timezone select", () => {
  it("groups zones by region and narrows them with search", () => {
    const onChange = vi.fn()
    render(<TimezoneSelect value="Europe/London" onChange={onChange} />)
    const select = screen.getByLabelText<HTMLSelectElement>("Timezone")
    expect(select.value).toBe("Europe/London")
    expect(select.querySelector("optgroup[label='Asia']")).toBeTruthy()
    fireEvent.change(screen.getByLabelText("Search timezones"), {
      target: { value: "karachi" },
    })
    const groups = [...select.querySelectorAll("optgroup")].map((g) => g.label)
    expect(groups).toEqual(["Asia"])
    fireEvent.change(select, { target: { value: "Asia/Karachi" } })
    expect(onChange).toHaveBeenCalledWith("Asia/Karachi")
    expect(select.getAttribute("aria-invalid")).toBeNull()
  })

  it("flags a stored zone that is not valid", () => {
    render(<TimezoneSelect value="Mars/Olympus" onChange={() => {}} />)
    expect(screen.getByLabelText("Timezone").getAttribute("aria-invalid")).toBe(
      "true",
    )
    expect(screen.getByText("Choose a timezone from the list.")).toBeTruthy()
  })

  it("matches spaces in a search against underscores", () => {
    expect(groupZones("new york")).toEqual([["America", ["America/New_York"]]])
  })
})
