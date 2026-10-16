import { Navigate, Outlet } from "react-router"
import { ApiError } from "@/lib/api"
import { useMe } from "./useMe"

export function AuthGuard() {
  const { isPending, error } = useMe()
  if (isPending) return null
  if (error instanceof ApiError && error.status === 401) {
    return <Navigate to="/login" replace />
  }
  if (error) {
    return (
      <p className="p-6 text-sm text-destructive">
        Cannot reach the Achilles server.
      </p>
    )
  }
  return <Outlet />
}
