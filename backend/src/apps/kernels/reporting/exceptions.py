from __future__ import annotations


class ReportingError(Exception):
    pass


class DatasetNotFoundError(ReportingError):
    pass


class ReportingValidationError(ReportingError):
    pass


class DatasetPermissionDenied(ReportingError):
    pass


class DatasetScopeError(ReportingError):
    pass


class DatasetExecutionError(ReportingError):
    pass

