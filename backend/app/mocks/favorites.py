_favorites: set[str] = {"005930", "TSLA"}


def get_favorites() -> list[str]:
    return list(_favorites)


def add_favorite(ticker: str) -> bool:
    _favorites.add(ticker)
    return True


def remove_favorite(ticker: str) -> bool:
    _favorites.discard(ticker)
    return True


def is_favorite(ticker: str) -> bool:
    return ticker in _favorites
