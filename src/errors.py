class DestinationError(RuntimeError):
    def __init__(self, code: str, message: str):
        super().__init__(message)
        self.code = code


class SourceRetrievalError(RuntimeError):
    """A safe, actionable error raised while reading public source metadata/media."""

    def __init__(
        self,
        code: str,
        message: str,
        stage: str,
        *,
        retryable: bool = False,
        retry_after: float | None = None,
        attempts: int | None = None,
    ):
        super().__init__(message)
        self.code = code
        self.stage = stage
        self.retryable = retryable
        self.retry_after = retry_after
        self.attempts = attempts
