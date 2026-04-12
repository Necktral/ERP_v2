from __future__ import annotations

from collections import defaultdict

from django.urls.resolvers import URLResolver

from config import urls as project_urls


def test_no_top_level_route_prefix_collisions() -> None:
    prefix_to_modules: dict[str, set[str]] = defaultdict(set)
    for item in project_urls.urlpatterns:
        if not isinstance(item, URLResolver):
            continue
        prefix = f"/{item.pattern}"
        module = item.urlconf_name if isinstance(item.urlconf_name, str) else type(item.urlconf_name).__name__
        prefix_to_modules[prefix].add(str(module))

    collisions = {prefix: sorted(modules) for prefix, modules in prefix_to_modules.items() if len(modules) > 1}
    assert collisions == {}
