import { Skeleton } from "@/components/ui/skeleton"

export function TodaySkeleton() {
  return (
    <div className="flex flex-col gap-4" data-testid="today-skeleton">
      <Skeleton className="h-56 w-full" />
      <div className="grid gap-4 md:grid-cols-2">
        <Skeleton className="h-28" />
        <Skeleton className="h-28" />
      </div>
      <Skeleton className="h-5 w-24" />
      <Skeleton className="h-10 w-full" />
      <Skeleton className="h-10 w-full" />
    </div>
  )
}
