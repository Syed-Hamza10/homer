import { Navigate, Outlet } from "react-router"
import { ErrorNotice } from "@/components/ErrorNotice"
import { ApiError } from "@/lib/api"
import { useMe } from "./useMe"

export function AuthGuard() {
  const { isPending, error, refetch } = useMe()
  if (isPending) return null
  if (error instanceof ApiError && error.status === 401) {
    return <Navigate to="/login" replace />
  }
  if (error) {
    return (
      <ErrorNotice
        error={error}
        onRetry={() => void refetch()}
        className="p-6"
      />
    )
  }
  return <Outlet />
}
