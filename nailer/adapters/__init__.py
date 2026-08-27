from nailer.adapters.base import LeagueAdapter, LeagueAdapterError
from nailer.cache import Cache
from nailer.config import NailerConfig

__all__ = ["LeagueAdapter", "LeagueAdapterError", "build_adapters"]


def build_adapters(config: NailerConfig, cache: Cache) -> dict[str, LeagueAdapter]:
    """Construct one adapter per enabled league in config."""
    adapters: dict[str, LeagueAdapter] = {}

    if config.espn:
        from nailer.adapters.espn import EspnAdapter

        adapters["espn"] = EspnAdapter(config.espn, cache=cache)

    if config.yahoo:
        from nailer.adapters.yahoo import YahooAdapter

        adapters["yahoo"] = YahooAdapter(config.yahoo, cache=cache)

    return adapters
