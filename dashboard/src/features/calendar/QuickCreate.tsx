import { useState } from "react"
import type { Approval } from "@/features/approvals/types"
import { EventForm } from "./EventForm"
import { toFields } from "./formValue"
import { PanelFrame } from "./PanelFrame"
import type { FormValue } from "./types"
import { useCreateEvent } from "./useCalendar"

type Props = {
  initial: FormValue
  onClose: () => void
  onApproval: (approval: Approval) => void
}

export function QuickCreate({ initial, onClose, onApproval }: Props) {
  const [value, setValue] = useState(initial)
  const create = useCreateEvent()

  return (
    <PanelFrame eyebrow="New event" testId="quick-create" onClose={onClose}>
      <EventForm
        value={value}
        onChange={setValue}
        onBack={onClose}
        submitLabel="Review event"
        busy={create.isPending}
        error={create.error}
        onSubmit={() =>
          create.mutate(toFields(value), { onSuccess: onApproval })
        }
      />
    </PanelFrame>
  )
}
