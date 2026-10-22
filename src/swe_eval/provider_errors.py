"""Secret-free structured failures. Never persist raw upstream messages or bodies."""
class ProviderError(RuntimeError):
    def __init__(self, message='provider request failed', *, category='unknown', status=None,
                 retryable=False, retry_after=None, ambiguous=False, provider_code=None):
        super().__init__(message)
        self.category, self.status, self.provider_code = category, status, provider_code
        self.retryable, self.retry_after, self.ambiguous = retryable, retry_after, ambiguous

class CompatibilityError(ProviderError):
    pass

class BudgetExceeded(ProviderError):
    pass

class ActionFormatError(ProviderError):
    pass
