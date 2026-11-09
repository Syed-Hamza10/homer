import { cleanup, render, screen } from "@testing-library/react"
import { afterEach, describe, expect, it, vi } from "vitest"
import { MODEL_DOC, ModelHint } from "./ModelHint"
import { useHealth } from "./useSettings"

vi.mock("./useSettings", () => ({ useHealth: vi.fn() }))

afterEach(cleanup)

const withStatus = (model_status: string) =>
  vi.mocked(useHealth).mockReturnValue({
    data: { model_status },
  } as unknown as ReturnType<typeof useHealth>)

describe("model hint", () => {
  it("tells the user to start the model when it is stopped", () => {
    withStatus("stopped")
    render(<ModelHint />)
    expect(screen.getByTestId("model-hint").textContent).toContain(
      "The AI model isn't running. Start Ollama and try again.",
    )
    expect(screen.getByRole("link").getAttribute("href")).toBe(MODEL_DOC)
  })

  it("stays hidden while the model runs", () => {
    withStatus("running")
    render(<ModelHint />)
    expect(screen.queryByTestId("model-hint")).toBeNull()
  })
})
