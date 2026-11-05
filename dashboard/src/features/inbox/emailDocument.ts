import DOMPurify from "dompurify"

const REMOTE = /^\s*(https?:)?\/\//i
const LINK = /^\s*(https?:|mailto:)/i
const FORBID_TAGS = ["style", "form", "input", "button", "textarea", "select"]
const FORBID_ATTR = ["srcset", "background", "poster", "action", "formaction"]

export function safeEmailHtml(html: string, showImages: boolean): string {
  const purifier = DOMPurify()
  purifier.addHook("afterSanitizeAttributes", (node) => {
    if (node.tagName === "A") {
      const href = node.getAttribute("href") ?? ""
      if (!LINK.test(href)) node.removeAttribute("href")
      node.setAttribute("target", "_blank")
      node.setAttribute("rel", "noopener noreferrer nofollow")
    }
    if (node.tagName === "IMG") {
      const src = node.getAttribute("src") ?? ""
      const inline = src.trim().toLowerCase().startsWith("data:image/")
      if (!inline && !(showImages && REMOTE.test(src)))
        node.removeAttribute("src")
    }
  })
  return purifier.sanitize(html, {
    FORBID_TAGS,
    FORBID_ATTR,
    ADD_ATTR: ["target"],
  })
}

export function emailDocument(html: string, showImages: boolean): string {
  const images = showImages ? "data: https:" : "data:"
  const policy = `default-src 'none'; img-src ${images}; style-src 'unsafe-inline'; font-src data:`
  return `<!doctype html><html><head><meta charset="utf-8"><meta http-equiv="Content-Security-Policy" content="${policy}"><base target="_blank"><style>body{margin:0;padding:12px;background:#fff;font:14px/1.55 system-ui,sans-serif;color:#1f1d1a;overflow-wrap:anywhere}img{max-width:100%;height:auto}table{max-width:100%}</style></head><body>${safeEmailHtml(html, showImages)}</body></html>`
}
