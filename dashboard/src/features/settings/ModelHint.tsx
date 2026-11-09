import { useHealth } from "./useSettings"

export const MODEL_DOC =
  "https://github.com/Syed-Hamza10/homer/blob/main/CLIENT_ONBOARDING.md#8-troubleshooting"

export function ModelHint() {
  const { data } = useHealth()
  if (!data || data.model_status !== "stopped") return null
  return (
    <div
      role="alert"
      className="rounded-md border border-destructive/40 p-4 text-sm"
      data-testid="model-hint"
    >
      <p className="font-medium">Start model</p>
      <p className="text-muted-foreground">
        The AI model isn't running. Start Ollama and try again.{" "}
        <a
          href={MODEL_DOC}
          target="_blank"
          rel="noreferrer"
          className="underline underline-offset-2"
        >
          How to start it
        </a>
      </p>
    </div>
  )
}
