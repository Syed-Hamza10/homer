import pytest


def pytest_collection_modifyitems(items: list[pytest.Item]) -> None:
    """Runs e2e after unit tests and browser tests last of all.

    The sync Playwright API leaves an event loop running for the rest of the session, and every
    asyncio test or fixture that starts after it fails with "cannot be called from a running loop".
    """
    items.sort(
        key=lambda item: (item.get_closest_marker("e2e") is not None, "page" in item.fixturenames)
    )
