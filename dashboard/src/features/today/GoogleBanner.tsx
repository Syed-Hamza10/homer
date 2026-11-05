import { Link } from "react-router"
import { bannerText } from "@/features/settings/googleStatus"
import type { GoogleStatus } from "@/features/settings/types"

export function GoogleBanner({ status }: { status: GoogleStatus | undefined }) {
  const text = bannerText(status)
  if (!text) return null
  return (
    <Link
      to="/settings"
      className="rounded-md border border-destructive/30 bg-destructive/10 px-3.5 py-2.5 text-sm text-destructive hover:bg-destructive/15"
      data-testid="google-banner"
    >
      {text}
    </Link>
  )
}
