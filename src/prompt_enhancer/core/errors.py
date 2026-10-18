"""Content-free failures shared by components and execution adapters."""


class CoreError(Exception):
    def __init__(self, code: str, *, uncertain: bool = False, operation_id: str | None = None):
        self.code = code
        self.uncertain = uncertain
        self.operation_id = operation_id
        super().__init__(code)
