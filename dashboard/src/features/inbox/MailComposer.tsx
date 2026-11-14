import { Sparkles } from "lucide-react"
import { useEffect, useState } from "react"
import { Button } from "@/components/ui/button"
import { ErrorNotice } from "@/components/ErrorNotice"
import { Input } from "@/components/ui/input"
import { Textarea } from "@/components/ui/textarea"
import { holdImeEnter } from "@/lib/ime"
import { ApprovalCard } from "@/features/approvals/ApprovalCard"
import { FormField } from "@/features/approvals/FormField"
import type { Approval } from "@/features/approvals/types"
import { clearDraft, saveDraft } from "./drafts"
import { splitQuote } from "./format"
import type { ComposeDraft } from "./types"
import { useCompose, useMailRefresh, useWriteWithHomer } from "./useMail"

type Props = {
  initial: ComposeDraft
  title: string
  slot: string
  restored?: boolean
  onClose: () => void
}

type Fields = { to: string; subject: string; text: string }

export function MailComposer({
  initial,
  title,
  slot,
  restored = false,
  onClose,
}: Props) {
  const parts = splitQuote(initial.body)
  const [fields, setFields] = useState<Fields>({
    to: initial.to,
    subject: initial.subject,
    text: parts.text,
  })
  const { to, subject, text } = fields
  const [instruction, setInstruction] = useState("")
  const [approval, setApproval] = useState<Approval | null>(null)
  const compose = useCompose()
  const write = useWriteWithHomer()
  const refresh = useMailRefresh()
  const [touched, setTouched] = useState(false)
  const body = text + parts.quote
  const edit = (change: Partial<Fields>) => {
    setTouched(true)
    setFields((current) => ({ ...current, ...change }))
  }
  const review = (draft: ComposeDraft) =>
    compose.mutate(draft, {
      onSuccess: (created) => {
        clearDraft(slot)
        setApproval(created)
      },
    })
  const writeBody = (args: Parameters<typeof write.mutate>[0]) =>
    write.mutate(args, { onSuccess: (written) => edit({ text: written.body }) })

  useEffect(() => {
    if (touched)
      saveDraft(slot, {
        to,
        subject,
        body,
        thread_id: initial.thread_id,
        title,
      })
  }, [touched, slot, to, subject, body, initial.thread_id, title])
  const discard = () => {
    clearDraft(slot)
    onClose()
  }

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
      onKeyDown={holdImeEnter}
      onSubmit={(event) => {
        event.preventDefault()
        review({ to, subject, body, thread_id: initial.thread_id })
      }}
    >
      <p className="text-xs font-medium text-muted-foreground">
        {title}
        {restored && !touched && (
          <span className="font-normal"> · Draft restored</span>
        )}
      </p>
      <FormField label="To">
        <Input
          value={to}
          onChange={(event) => edit({ to: event.target.value })}
          placeholder="name@example.com, another@example.com"
          required
        />
      </FormField>
      <FormField label="Subject">
        <Input
          value={subject}
          onChange={(event) => edit({ subject: event.target.value })}
        />
      </FormField>
      <FormField label="Message">
        <Textarea
          value={text}
          onChange={(event) => edit({ text: event.target.value })}
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
            writeBody({
              instruction: instruction.trim(),
              thread_id: initial.thread_id,
              to,
            })
          }
        >
          {write.isPending ? "Writing…" : "Draft with Homer"}
        </Button>
      </div>
      <ErrorNotice
        error={compose.error ?? write.error}
        onRetry={() => {
          if (compose.error && compose.variables) review(compose.variables)
          else if (write.variables) writeBody(write.variables)
        }}
      />
      <div className="flex gap-2">
        <Button size="sm" type="submit" disabled={compose.isPending || !to}>
          Review email
        </Button>
        <Button size="sm" type="button" variant="outline" onClick={discard}>
          Discard
        </Button>
      </div>
      <p className="text-xs text-muted-foreground">
        Review email saves a Gmail draft and shows it to you. Nothing goes out
        until you press Send email.
      </p>
    </form>
  )
}
