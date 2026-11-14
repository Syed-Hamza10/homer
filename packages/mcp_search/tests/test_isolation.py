from pathlib import Path

from homer_mcp_search.settings import homer_home


def test_tests_never_touch_the_real_homer_home() -> None:
    assert homer_home() != Path("~/.homer").expanduser()
    assert homer_home().name.startswith("homer-test-home-")
