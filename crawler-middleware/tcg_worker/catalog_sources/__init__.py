"""Publisher and maintainer catalog adapters. Data files stay in the operator's private cache."""
from .bulk import pokemon, riftbound, weiss, yugioh
from .nivel import nivel
from .onepiece import onepiece
from .transport import CatalogHTTP


_ADAPTERS = {"YUGIOH": yugioh, "POKEMON": pokemon, "WEISS": weiss, "NIVEL": nivel, "RIFTBOUND": riftbound,
             "ONEPIECE": onepiece}
CATALOG_GAMES = frozenset(_ADAPTERS)


def iter_catalog(game_code, *, legacy_editions=None):
    if game_code not in _ADAPTERS:
        raise ValueError(f"Unknown catalog game {game_code!r}")
    http = CatalogHTTP()
    with http.scan(game_code):
        if game_code == "YUGIOH" and legacy_editions is not None:
            yield from yugioh(http, legacy_editions)
        else:
            yield from _ADAPTERS[game_code](http)
