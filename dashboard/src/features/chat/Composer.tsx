import { useState, type KeyboardEvent } from "react"
import { Button } from "@/components/ui/button"
import { Textarea } from "@/components/ui/textarea"

type Props = { disabled: boolean; onSend: (message: string) => void }

export function Composer({ disabled, onSend }: Props) {
  const [value, setValue] = useState("")

  const submit = () => {
    const message = value.trim()
    if (!message || disabled) return
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
    <div className="flex items-end gap-2">
      <Textarea
        value={value}
        onChange={(event) => setValue(event.target.value)}
        onKeyDown={onKeyDown}
        placeholder="Message Achilles"
        rows={2}
        className="max-h-40 resize-none"
      />
      <Button onClick={submit} disabled={disabled || !value.trim()}>
        Send
      </Button>
    </div>
  )
}
