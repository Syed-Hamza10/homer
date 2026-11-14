import { ArrowUp, Square } from "lucide-react"
import { useState, type KeyboardEvent, type Ref } from "react"
import { Button } from "@/components/ui/button"
import { Textarea } from "@/components/ui/textarea"

type Props = {
  streaming: boolean
  onSend: (message: string) => void
  onStop: () => void
  inputRef?: Ref<HTMLTextAreaElement>
}

export function Composer({ streaming, onSend, onStop, inputRef }: Props) {
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
    <div className="flex items-end gap-2 rounded-2xl border border-border bg-card py-1.5 pr-1.5 pl-2 shadow-[0_1px_2px_oklch(0_0_0/0.04),inset_0_1px_0_var(--marble-1)] transition-shadow focus-within:border-ring/60 focus-within:ring-3 focus-within:ring-ring/15">
      <Textarea
        ref={inputRef}
        value={value}
        onChange={(event) => setValue(event.target.value)}
        onKeyDown={onKeyDown}
        placeholder="Message Homer"
        aria-label="Message Homer"
        rows={1}
        className="max-h-48 min-h-9 resize-none border-0 bg-transparent px-2 py-1.5 text-[15px] shadow-none focus-visible:border-0 focus-visible:ring-0 md:text-[15px] dark:bg-transparent"
      />
      {streaming ? (
        <Button
          variant="outline"
          size="icon"
          aria-label="Stop"
          title="Stop"
          onClick={onStop}
          className="size-9 shrink-0 rounded-xl"
        >
          <Square className="size-3 fill-current" strokeWidth={1.8} />
        </Button>
      ) : (
        <Button
          variant="brand"
          size="icon"
          aria-label="Send"
          title="Send"
          onClick={submit}
          disabled={!value.trim()}
          className="size-9 shrink-0 rounded-xl"
        >
          <ArrowUp className="size-4" strokeWidth={2} />
        </Button>
      )}
    </div>
  )
}
