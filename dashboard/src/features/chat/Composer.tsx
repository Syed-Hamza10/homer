import { Square } from "lucide-react"
import { useState, type KeyboardEvent } from "react"
import { Button } from "@/components/ui/button"
import { Textarea } from "@/components/ui/textarea"

type Props = {
  streaming: boolean
  onSend: (message: string) => void
  onStop: () => void
}

export function Composer({ streaming, onSend, onStop }: Props) {
  const [value, setValue] = useState("")

  const submit = () => {
    const message = value.trim()
    if (!message || streaming) return
    onSend(message)
    setValue("")
  }

  const onKeyDown = (event: KeyboardEvent<HTMLTextAreaElement>) => {
    if (event.key === "Enter" && !event.shiftKey) {
      event.preventDefault()
      submit()
    }
  }

  return (
    <div className="rounded-lg border border-border bg-card/80 p-2 shadow-[inset_0_1px_0_var(--marble-1)] transition-shadow focus-within:border-ring/60 focus-within:ring-3 focus-within:ring-ring/20">
      <Textarea
        value={value}
        onChange={(event) => setValue(event.target.value)}
        onKeyDown={onKeyDown}
        placeholder="Message Homer"
        rows={2}
        className="max-h-40 resize-none border-0 bg-transparent px-2 py-1.5 shadow-none focus-visible:border-0 focus-visible:ring-0 dark:bg-transparent"
      />
      <div className="flex items-end justify-between gap-3 px-1">
        <span className="hidden pb-1 text-[9px] font-medium tracking-[0.2em] uppercase text-muted-foreground sm:block">
          Enter to send · Shift+Enter for a new line
        </span>
        {streaming ? (
          <Button variant="outline" onClick={onStop}>
            <Square className="size-3 fill-current" strokeWidth={1.8} />
            Stop
          </Button>
        ) : (
          <Button onClick={submit} disabled={!value.trim()}>
            Send
          </Button>
        )}
      </div>
    </div>
  )
}
