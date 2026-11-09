import { Sparkles } from "lucide-react"
import { useState } from "react"
import { Button } from "@/components/ui/button"
import { errorText } from "@/lib/errorText"
import { Input } from "@/components/ui/input"
import { Textarea } from "@/components/ui/textarea"
import { ApprovalCard } from "@/features/approvals/ApprovalCard"
import { FormField } from "@/features/approvals/FormField"
import type { Approval } from "@/features/approvals/types"
import { splitQuote } from "./format"
import type { ComposeDraft } from "./types"
import { useCompose, useMailRefresh, useWriteWithHomer } from "./useMail"

type Props = {
  initial: ComposeDraft
  title: string
  onClose: () => void
}

export function MailComposer({ initial, title, onClose }: Props) {
  const parts = splitQuote(initial.body)
  const [to, setTo] = useState(initial.to)
  const [subject, setSubject] = useState(initial.subject)
  const [text, setText] = useState(parts.text)
  const [instruction, setInstruction] = useState("")
  const [approval, setApproval] = useState<Approval | null>(null)
  const compose = useCompose()
  const write = useWriteWithHomer()
  const refresh = useMailRefresh()

  if (approval)
    return (
      <section data-testid="composer-approval" className="flex flex-col gap-2">
        <ApprovalCard approval={approval} onDecided={() => void refresh()} />
        <Button
          size="xs"
          variant="ghost"
          className="self-start"
          onClick={onClose}
        >
          Close
        </Button>
      </section>
    )

  return (
    <form
      data-testid="composer"
      className="flex flex-col gap-3 rounded-lg border border-border bg-card/60 p-4 shadow-[inset_0_1px_0_var(--marble-1)]"
      onSubmit={(event) => {
        event.preventDefault()
        compose.mutate(
          {
            to,
            subject,
            body: text + parts.quote,
            thread_id: initial.thread_id,
          },
          { onSuccess: setApproval },
        )
      }}
    >
      <p className="text-xs font-medium text-muted-foreground">{title}</p>
      <FormField label="To">
        <Input
          value={to}
          onChange={(event) => setTo(event.target.value)}
          placeholder="name@example.com, another@example.com"
          required
        />
      </FormField>
      <FormField label="Subject">
        <Input
          value={subject}
          onChange={(event) => setSubject(event.target.value)}
        />
      </FormField>
      <FormField label="Message">
        <Textarea
          value={text}
          onChange={(event) => setText(event.target.value)}
          className="min-h-36"
        />
      </FormField>
      {parts.quote && (
        <details className="text-xs text-muted-foreground">
          <summary className="cursor-pointer">Quoted text</summary>
          <p className="mt-2 whitespace-pre-wrap">{parts.quote.trim()}</p>
        </details>
      )}
      <div className="flex flex-wrap items-center gap-2 rounded-md border border-dashed border-border px-2 py-2">
        <Sparkles className="size-4 text-muted-foreground" />
        <Input
          aria-label="Instruction for Homer"
          placeholder="Tell Homer what to say, e.g. accept Thursday at 2pm"
          value={instruction}
          onChange={(event) => setInstruction(event.target.value)}
          className="min-w-48 flex-1"
        />
        <Button
          size="sm"
          type="button"
          variant="outline"
          disabled={!instruction.trim() || write.isPending}
          onClick={() =>
            write.mutate(
              {
                instruction: instruction.trim(),
                thread_id: initial.thread_id,
                to,
              },
              { onSuccess: (written) => setText(written.body) },
            )
          }
        >
          {write.isPending ? "Writing…" : "Draft with Homer"}
        </Button>
      </div>
      {(compose.error ?? write.error) && (
        <p className="text-sm text-destructive">
          {errorText(compose.error ?? write.error)}
        </p>
      )}
      <div className="flex gap-2">
        <Button size="sm" type="submit" disabled={compose.isPending || !to}>
          Send
        </Button>
        <Button size="sm" type="button" variant="outline" onClick={onClose}>
          Discard
        </Button>
      </div>
      <p className="text-xs text-muted-foreground">
        Send saves a Gmail draft and asks for your approval before anything goes
        out.
      </p>
    </form>
  )
}
