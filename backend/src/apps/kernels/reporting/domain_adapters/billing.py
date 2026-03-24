from __future__ import annotations

from apps.kernels.reporting.exceptions import DatasetExecutionError


def run_dataset(*, dataset_key: str, company, branch, filters: dict):
    raise DatasetExecutionError(
        f"Billing adapter no disponible en este corte (R0-R2): {dataset_key}"
    )
