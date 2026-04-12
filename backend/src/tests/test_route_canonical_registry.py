from __future__ import annotations

from typing import Any, cast

from django.urls.resolvers import URLResolver

from config import urls as project_urls
from config.routing_policy import routing_prefix_contract


def _top_level_prefixes() -> set[str]:
    prefixes: set[str] = set()
    for item in project_urls.urlpatterns:
        if isinstance(item, URLResolver):
            prefixes.add(f"/{item.pattern}")
    return prefixes


def test_routing_policy_prefixes_are_mounted() -> None:
    mounted = _top_level_prefixes()
    contract = routing_prefix_contract()

    fuel = cast(dict[str, Any], contract["fuel"])
    assert fuel["canonical_prefix"] in mounted
    for prefix in cast(list[str], fuel["allowed_legacy_prefixes"]):
        assert prefix in mounted

    billing = cast(dict[str, Any], contract["billing"])
    assert billing["canonical_prefix"] in mounted
    for prefix in cast(list[str], billing["allowed_legacy_prefixes"]):
        assert prefix in mounted
