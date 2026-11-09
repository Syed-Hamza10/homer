import type { ReactNode } from "react"
import { X } from "lucide-react"
import { Button } from "@/components/ui/button"
import { Card, CardContent } from "@/components/ui/card"

type Props = {
  eyebrow: string
  testId: string
  onClose: () => void
  children: ReactNode
}

export function PanelFrame({ eyebrow, testId, onClose, children }: Props) {
  return (
    <Card size="sm" data-testid={testId}>
      <CardContent className="flex flex-col gap-3">
        <div className="flex items-center justify-between gap-2">
          <p className="text-xs font-medium text-muted-foreground">{eyebrow}</p>
          <Button
            size="icon-xs"
            variant="ghost"
            aria-label="Close"
            onClick={onClose}
          >
            <X />
          </Button>
        </div>
        {children}
      </CardContent>
    </Card>
  )
}
