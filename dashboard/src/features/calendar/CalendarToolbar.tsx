import { ChevronLeft, ChevronRight } from "lucide-react"
import { Button } from "@/components/ui/button"
import type { View } from "./types"

type Props = {
  title: string
  view: View
  onView: (view: View) => void
  onToday: () => void
  onStep: (step: number) => void
  onFindTime: () => void
}

const VIEWS: { view: View; label: string }[] = [
  { view: "day", label: "Day" },
  { view: "week", label: "Week" },
  { view: "month", label: "Month" },
]

export function CalendarToolbar({
  title,
  view,
  onView,
  onToday,
  onStep,
  onFindTime,
}: Props) {
  return (
    <div className="flex flex-wrap items-center justify-between gap-2">
      <div className="flex items-center gap-1.5">
        <Button size="sm" variant="outline" onClick={onToday}>
          Today
        </Button>
        <Button
          size="icon-sm"
          variant="ghost"
          aria-label="Previous"
          onClick={() => onStep(-1)}
        >
          <ChevronLeft />
        </Button>
        <Button
          size="icon-sm"
          variant="ghost"
          aria-label="Next"
          onClick={() => onStep(1)}
        >
          <ChevronRight />
        </Button>
        <h2
          data-testid="calendar-title"
          className="ml-1 font-heading text-lg leading-none"
        >
          {title}
        </h2>
      </div>
      <div className="flex items-center gap-1.5">
        <div className="flex rounded-md border border-border p-0.5">
          {VIEWS.map((item) => (
            <Button
              key={item.view}
              size="xs"
              variant={item.view === view ? "secondary" : "ghost"}
              aria-pressed={item.view === view}
              onClick={() => onView(item.view)}
            >
              {item.label}
            </Button>
          ))}
        </div>
        <Button size="sm" variant="outline" onClick={onFindTime}>
          Find a time
        </Button>
      </div>
    </div>
  )
}
