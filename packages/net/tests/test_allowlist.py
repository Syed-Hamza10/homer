import pytest

from achilles_net import Allowlist, BlockedHostError


def test_allowed_host_passes() -> None:
    Allowlist(["api.example.com"]).check("https://api.example.com/v1/ping?x=1")


def test_blocked_host_raises_with_host() -> None:
    with pytest.raises(BlockedHostError) as excinfo:
        Allowlist(["api.example.com"]).check("https://evil.example.com/")
    assert excinfo.value.host == "evil.example.com"


def test_host_match_is_case_insensitive() -> None:
    Allowlist(["API.Example.COM"]).check("https://api.EXAMPLE.com/")


def test_non_default_port_is_part_of_the_match() -> None:
    allowlist = Allowlist(["127.0.0.1:11434"])
    allowlist.check("http://127.0.0.1:11434/api/tags")
    with pytest.raises(BlockedHostError) as excinfo:
        allowlist.check("http://127.0.0.1/api/tags")
    assert excinfo.value.host == "127.0.0.1"


def test_host_without_port_does_not_allow_other_ports() -> None:
    with pytest.raises(BlockedHostError) as excinfo:
        Allowlist(["127.0.0.1"]).check("http://127.0.0.1:11434/api/tags")
    assert excinfo.value.host == "127.0.0.1:11434"


def test_explicit_default_port_matches_bare_host() -> None:
    Allowlist(["api.example.com"]).check("https://api.example.com:443/")
    Allowlist(["api.example.com"]).check("http://api.example.com:80/")


def test_localhost_is_not_an_alias_for_the_loopback_address() -> None:
    with pytest.raises(BlockedHostError):
        Allowlist(["127.0.0.1:11434"]).check("http://localhost:11434/")


def test_url_without_host_is_blocked() -> None:
    with pytest.raises(BlockedHostError):
        Allowlist(["api.example.com"]).check("/relative/path")
