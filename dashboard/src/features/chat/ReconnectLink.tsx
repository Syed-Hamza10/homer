import { Link } from "react-router"
import { Button } from "@/components/ui/button"

type Props = { url: string }

export function ReconnectLink({ url }: Props) {
  return (
    <Button asChild variant="outline" size="sm" className="self-start">
      <Link to={url}>Reconnect Google</Link>
    </Button>
  )
}
