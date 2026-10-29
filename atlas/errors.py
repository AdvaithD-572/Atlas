class AtlasError(Exception):
    """An intentional, client-safe application failure."""

    def __init__(self, code: str, message: str, status: int = 422) -> None:
        self.code = code
        self.message = message
        self.status = status
        super().__init__(message)


def not_found() -> AtlasError:
    return AtlasError("not_found", "Resource not found.", 404)
