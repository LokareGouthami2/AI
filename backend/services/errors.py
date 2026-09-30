class AppError(Exception):
    """Domain error mapped to the API error envelope."""

    def __init__(self, status: int, code: str, message: str, details: dict | None = None):
        super().__init__(message)
        self.status = status
        self.code = code
        self.message = message
        self.details = details or {}


def not_found(what: str = "Document") -> AppError:
    return AppError(404, "NOT_FOUND", f"{what} not found.")
