import { describe, expect, it } from "vitest"
import { ApiError } from "./api"
import { errorText } from "./errorText"

describe("errorText", () => {
  it("says what went wrong in plain English, never a bare status code", () => {
    for (const status of [400, 401, 403, 404, 409, 422, 500, 502, 503]) {
      const text = errorText(new ApiError(status))
      expect(text).not.toMatch(/request failed|\d{3}/i)
    }
    expect(errorText(new ApiError(404))).toBe(
      "That could not be found. It may have been moved or deleted.",
    )
    expect(errorText(new TypeError("fetch failed"))).toContain(
      "Cannot reach the Homer server",
    )
    expect(errorText(null)).toBeNull()
  })
})
