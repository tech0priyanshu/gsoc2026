class PipelineError(Exception):
    pass


class CycleDetectedError(PipelineError):
    pass


class InvalidPipelineError(PipelineError):
    pass


class NodeTimeoutError(PipelineError):
    """Raised when a node exceeds its configured timeout."""
    pass


class NodeAbortedError(PipelineError):
    """Raised when a node is aborted via an external event."""
    pass


class PipelineAbortedError(PipelineError):
    """Raised when the pipeline is aborted via pipeline.abort()."""
    pass


class AmbiguousStepName(PipelineError):
    """Raised when a short step name matches multiple registered entries."""
    pass
