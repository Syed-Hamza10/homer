import { useState } from "react"
import { PageHeader } from "@/components/PageHeader"
import { ScrollArea } from "@/components/ui/scroll-area"
import { ApprovalCard } from "./ApprovalCard"
import type { Approval } from "./types"
import { useApprovals } from "./useApprovals"

export function ApprovalsPage() {
  const { data: pending = [], isPending } = useApprovals()
  const [decided, setDecided] = useState<Approval[]>([])
  const add = (approval: Approval) => setDecided((list) => [approval, ...list])

  return (
    <ScrollArea className="min-h-0 flex-1">
      <main className="mx-auto flex max-w-3xl flex-col gap-7 p-6">
        <PageHeader
          eyebrow="Consent"
          title="Approvals"
          description="Actions that need your signature before Homer carries them out."
        />
        <section className="flex flex-col gap-3">
          <h2 className="text-[9px] font-medium tracking-[0.3em] uppercase text-muted-foreground">
            Pending
          </h2>
          {!isPending && pending.length === 0 && (
            <div className="flex flex-col items-center gap-3 rounded-lg border border-dashed border-border/80 px-6 py-12 text-center">
              <span
                aria-hidden
                className="size-2 rotate-45 border border-ring/60"
              />
              <p className="text-sm text-muted-foreground">
                Nothing is waiting for you.
              </p>
            </div>
          )}
          {pending.map((approval) => (
            <ApprovalCard
              key={approval.id}
              approval={approval}
              onDecided={add}
            />
          ))}
        </section>
        {decided.length > 0 && (
          <section className="flex flex-col gap-2">
            <h2 className="text-[9px] font-medium tracking-[0.3em] uppercase text-muted-foreground">
              Decided this session
            </h2>
            <ul className="flex flex-col gap-1 text-sm">
              {decided.map((approval) => (
                <li
                  key={approval.id}
                  data-testid={`decided-${approval.id}`}
                  className="flex justify-between gap-4 rounded-md border border-border/70 bg-muted/40 px-3 py-2"
                >
                  <span className="truncate">
                    #{approval.id} · {approval.action} · {approval.preview}
                  </span>
                  <span className="font-medium">{approval.status}</span>
                </li>
              ))}
            </ul>
          </section>
        )}
      </main>
    </ScrollArea>
  )
}
