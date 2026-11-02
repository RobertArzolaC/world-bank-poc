"""Domain errors shared by the catalog, rules, service, and tools."""


class QueryError(ValueError):
    """A request violates the demo's business rules and must not reach the API."""


class WorldBankAPIError(RuntimeError):
    """The World Bank API failed or returned a response the PoC cannot trust."""
