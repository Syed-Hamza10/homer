import { Check, Copy } from "lucide-react"
import { useState } from "react"
import { Button } from "@/components/ui/button"

type Props = { text: string; label?: string; className?: string }

export function CopyButton({ text, label = "Copy", className }: Props) {
  const [copied, setCopied] = useState(false)

  const copy = async () => {
    try {
      await navigator.clipboard.writeText(text)
      setCopied(true)
      setTimeout(() => setCopied(false), 1500)
    } catch {
      setCopied(false)
    }
  }

  return (
    <Button
      type="button"
      variant="ghost"
      size="icon-xs"
      aria-label={copied ? "Copied" : label}
      title={copied ? "Copied" : label}
      onClick={copy}
      className={className}
    >
      {copied ? <Check strokeWidth={1.8} /> : <Copy strokeWidth={1.8} />}
    </Button>
  )
}
