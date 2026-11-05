import { useMemo, useRef, useState } from "react"
import { emailDocument } from "./emailDocument"

type Props = { html: string; showImages: boolean }

const MIN_HEIGHT = 80

export function EmailBody({ html, showImages }: Props) {
  const frame = useRef<HTMLIFrameElement>(null)
  const [height, setHeight] = useState(MIN_HEIGHT)
  const srcDoc = useMemo(
    () => emailDocument(html, showImages),
    [html, showImages],
  )

  return (
    <iframe
      ref={frame}
      title="Message body"
      data-testid="message-html"
      sandbox="allow-same-origin allow-popups allow-popups-to-escape-sandbox"
      referrerPolicy="no-referrer"
      srcDoc={srcDoc}
      style={{ height }}
      className="w-full rounded-md border border-border/70 bg-white"
      onLoad={() => {
        const body = frame.current?.contentDocument?.body
        if (body) setHeight(Math.max(MIN_HEIGHT, body.scrollHeight + 24))
      }}
    />
  )
}
