import { useState } from "react"
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
      <main className="mx-auto flex max-w-3xl flex-col gap-6 p-6">
        <section className="flex flex-col gap-3">
          <h1 className="text-lg font-semibold">Pending approvals</h1>
          {!isPending && pending.length === 0 && (
            <p className="text-sm text-muted-foreground">
              Nothing is waiting for you.
            </p>
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
            <h2 className="text-sm font-semibold">Decided this session</h2>
            <ul className="flex flex-col gap-1 text-sm">
              {decided.map((approval) => (
                <li
                  key={approval.id}
                  data-testid={`decided-${approval.id}`}
                  className="flex justify-between gap-4 rounded-md bg-muted px-3 py-2"
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
