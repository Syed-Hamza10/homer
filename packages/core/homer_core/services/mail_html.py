from dataclasses import dataclass

import nh3

DROPPED_WITH_CONTENT = {"script", "style", "title", "noscript", "template"}
TAGS = (nh3.ALLOWED_TAGS | {"font", "center", "span", "div"}) - DROPPED_WITH_CONTENT
SHARED_ATTRIBUTES = {"style", "align", "valign", "width", "height", "dir", "title", "bgcolor"}
ATTRIBUTES = {
    "*": SHARED_ATTRIBUTES,
    "a": {"href", "name"},
    "img": {"src", "alt"},
    "font": {"face", "size", "color"},
    "table": {"border", "cellpadding", "cellspacing"},
    "td": {"colspan", "rowspan", "nowrap"},
    "th": {"colspan", "rowspan", "nowrap"},
}
STYLE_PROPERTIES = {
    "color",
    "background-color",
    "font",
    "font-family",
    "font-size",
    "font-style",
    "font-weight",
    "text-align",
    "text-decoration",
    "text-transform",
    "line-height",
    "letter-spacing",
    "white-space",
    "vertical-align",
    "display",
    "width",
    "max-width",
    "min-width",
    "height",
    "max-height",
    "margin",
    "margin-top",
    "margin-right",
    "margin-bottom",
    "margin-left",
    "padding",
    "padding-top",
    "padding-right",
    "padding-bottom",
    "padding-left",
    "border",
    "border-top",
    "border-right",
    "border-bottom",
    "border-left",
    "border-color",
    "border-style",
    "border-width",
    "border-collapse",
    "border-radius",
}
LINK_SCHEMES = ("http://", "https://", "mailto:")
REMOTE_SCHEMES = ("http://", "https://", "//")
INLINE_IMAGE = "data:image/"


@dataclass
class CleanHtml:
    html: str
    remote_images: int = 0


def sanitise(markup: str, show_images: bool = False) -> CleanHtml:
    """Allowlist sanitising for an email body: no scripts, handlers or styles that can fetch,
    links only to http(s) and mailto opening in a new tab, remote images dropped unless shown."""
    found = CleanHtml(html="")

    def keep(tag: str, attribute: str, value: str) -> str | None:
        lowered = value.strip().lower()
        if attribute == "href":
            return value if lowered.startswith(LINK_SCHEMES) else None
        if tag == "img" and attribute == "src":
            if lowered.startswith(INLINE_IMAGE):
                return value
            if lowered.startswith(REMOTE_SCHEMES):
                found.remote_images += 1
                return value if show_images else None
            return None
        return value

    found.html = nh3.clean(
        markup,
        tags=TAGS,
        clean_content_tags=DROPPED_WITH_CONTENT,
        attributes=ATTRIBUTES,
        attribute_filter=keep,
        url_schemes={"http", "https", "mailto", "data"},
        link_rel="noopener noreferrer nofollow",
        set_tag_attribute_values={"a": {"target": "_blank"}},
        filter_style_properties=STYLE_PROPERTIES,
    )
    return found
