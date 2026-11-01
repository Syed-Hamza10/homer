from pydantic_ai.toolsets import AbstractToolset, CombinedToolset, FilteredToolset

from homer_core.agent.agent import Deps

MAX_TOOLS = 10
DEFAULT_TOOLSET = "mail+calendar"

TOOLSETS: dict[str, tuple[str, ...]] = {
    "mail": (
        "mail_search",
        "mail_get",
        "mail_thread",
        "mail_draft",
        "mail_send",
        "mail_label",
        "mail_archive",
        "contacts_search",
        "now",
        "remind",
    ),
    "calendar": (
        "cal_list",
        "cal_find_free_slots",
        "cal_create",
        "cal_update",
        "cal_delete",
        "contacts_search",
        "now",
        "parse_datetime",
        "remind",
    ),
    "mail+calendar": (
        "mail_search",
        "mail_get",
        "mail_thread",
        "mail_draft",
        "mail_send",
        "cal_list",
        "cal_find_free_slots",
        "cal_create",
        "contacts_search",
        "now",
    ),
    "search": ("web_search", "fetch_page", "now", "remind"),
    "system": ("now", "parse_datetime", "remind"),
}

TIER_2_TOOLS = frozenset({"mail_label", "mail_archive"})


def build_toolsets(
    mcp: AbstractToolset[Deps], core: AbstractToolset[Deps]
) -> dict[str, AbstractToolset[Deps]]:
    base = CombinedToolset([mcp, core])
    return {
        name: FilteredToolset(base, lambda ctx, tool, allowed=names: tool.name in allowed)
        for name, names in TOOLSETS.items()
    }
