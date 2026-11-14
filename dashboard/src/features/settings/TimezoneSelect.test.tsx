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

  it("narrows the options as you type, picks the first on Enter, and restores on clear", () => {
    const onChange = vi.fn()
    render(<TimezoneSelect value="Europe/London" onChange={onChange} />)
    const select = screen.getByLabelText<HTMLSelectElement>("Timezone")
    const search = screen.getByLabelText("Search timezones")
    const all = select.querySelectorAll("option").length

    fireEvent.change(search, { target: { value: "KARA" } })
    const values = [...select.querySelectorAll("option")].map((o) => o.value)
    expect(values).toContain("Asia/Karachi")
    expect(values.length).toBeLessThan(all)
    expect(values.every((zone) => zone.toLowerCase().includes("kara"))).toBe(
      true,
    )
    expect(screen.getByText(/Enter picks Asia\/Karachi/)).toBeTruthy()

    fireEvent.change(search, { target: { value: "" } })
    expect(select.querySelectorAll("option").length).toBe(all)

    fireEvent.change(search, { target: { value: "kara" } })
    fireEvent.keyDown(search, { key: "Enter" })
    expect(onChange).toHaveBeenCalledWith("Asia/Karachi")
    expect((search as HTMLInputElement).value).toBe("")
  })

  it("matches a region name", () => {
    render(<TimezoneSelect value="UTC" onChange={() => {}} />)
    fireEvent.change(screen.getByLabelText("Search timezones"), {
      target: { value: "australia" },
    })
    const select = screen.getByLabelText<HTMLSelectElement>("Timezone")
    const groups = [...select.querySelectorAll("optgroup")].map((g) => g.label)
    expect(groups).toEqual(["Australia"])
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
