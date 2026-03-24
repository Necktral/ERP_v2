from __future__ import annotations

from rest_framework import status
from rest_framework.response import Response
from rest_framework.views import APIView

from apps.modulos.common.pagination import get_limit_offset, paginate_queryset
from apps.modulos.common.permissions import rbac_permission

from ..exceptions import (
    DatasetExecutionError,
    DatasetNotFoundError,
    DatasetPermissionDenied,
    DatasetScopeError,
    ReportingValidationError,
)
from ..models import ReportRun
from ..services import get_catalog_entry, list_catalog, run_dataset_from_request
from .filters import sanitize_filters
from .serializers import DatasetRunIn, RunsListIn


class CatalogListView(APIView):
    permission_classes = [rbac_permission("report.catalog.read")]

    def get(self, request):
        rows = [row for row in list_catalog() if row.get("is_enabled")]
        return Response({"count": len(rows), "results": rows}, status=status.HTTP_200_OK)


class CatalogDetailView(APIView):
    permission_classes = [rbac_permission("report.catalog.read")]

    def get(self, request, dataset_key: str):
        try:
            row = get_catalog_entry(dataset_key)
        except KeyError:
            return Response({"detail": "Dataset no encontrado."}, status=status.HTTP_404_NOT_FOUND)
        return Response(row, status=status.HTTP_200_OK)


class DatasetRunView(APIView):
    permission_classes = [rbac_permission("report.dataset.read")]

    def post(self, request, dataset_key: str):
        serializer = DatasetRunIn(data=request.data)
        serializer.is_valid(raise_exception=True)
        payload = serializer.validated_data
        try:
            envelope, run_id = run_dataset_from_request(
                request=request,
                dataset_key=dataset_key,
                filters=sanitize_filters(payload.get("filters")),
                consumer_ref=str(payload.get("consumer_ref") or ""),
            )
        except DatasetNotFoundError as exc:
            return Response({"detail": str(exc)}, status=status.HTTP_404_NOT_FOUND)
        except DatasetPermissionDenied as exc:
            return Response({"detail": str(exc)}, status=status.HTTP_403_FORBIDDEN)
        except (ReportingValidationError, DatasetScopeError) as exc:
            return Response({"detail": str(exc)}, status=status.HTTP_400_BAD_REQUEST)
        except DatasetExecutionError as exc:
            return Response({"detail": str(exc)}, status=status.HTTP_500_INTERNAL_SERVER_ERROR)

        body = dict(envelope)
        body["run_id"] = run_id
        return Response(body, status=status.HTTP_200_OK)


class RunsListView(APIView):
    permission_classes = [rbac_permission("report.run.read")]

    def get(self, request):
        serializer = RunsListIn(data=request.query_params)
        serializer.is_valid(raise_exception=True)
        dataset_key = str(serializer.validated_data.get("dataset_key") or "").strip()

        qs = ReportRun.objects.select_related("requested_by", "company", "branch").all().order_by("-created_at", "-id")
        if dataset_key:
            qs = qs.filter(dataset_key=dataset_key)
        company = getattr(request, "company", None)
        branch = getattr(request, "branch", None)
        if company is not None:
            qs = qs.filter(company=company)
        if branch is not None:
            qs = qs.filter(branch=branch)

        limit, offset = get_limit_offset(request)
        total, rows = paginate_queryset(qs, limit=limit, offset=offset)
        results = [
            {
                "run_id": str(row.run_id),
                "dataset_key": row.dataset_key,
                "status": row.status,
                "row_count": int(row.row_count or 0),
                "duration_ms": int(row.duration_ms or 0),
                "created_at": row.created_at,
                "completed_at": row.completed_at,
                "company_id": getattr(row.company, "id", None),
                "branch_id": getattr(row.branch, "id", None),
            }
            for row in rows
        ]
        return Response(
            {"count": int(total), "limit": int(limit), "offset": int(offset), "results": results},
            status=status.HTTP_200_OK,
        )


class RunDetailView(APIView):
    permission_classes = [rbac_permission("report.run.read")]

    def get(self, request, run_id: str):
        company = getattr(request, "company", None)
        branch = getattr(request, "branch", None)
        qs = ReportRun.objects.select_related("requested_by", "company", "branch").filter(run_id=run_id)
        if company is not None:
            qs = qs.filter(company=company)
        if branch is not None:
            qs = qs.filter(branch=branch)
        row = qs.first()
        if row is None:
            return Response({"detail": "Run no encontrado."}, status=status.HTTP_404_NOT_FOUND)
        return Response(
            {
                "run_id": str(row.run_id),
                "dataset_key": row.dataset_key,
                "status": row.status,
                "filters": row.filters_json,
                "row_count": int(row.row_count or 0),
                "duration_ms": int(row.duration_ms or 0),
                "result_hash": row.result_hash,
                "warnings": row.warnings_json,
                "source_summary": row.source_summary_json,
                "lineage": row.lineage_json,
                "schema_version": row.schema_version_used,
                "semantic_version": row.semantic_version_used,
                "consumer_type": row.consumer_type,
                "consumer_ref": row.consumer_ref,
                "error_detail": row.error_detail,
                "created_at": row.created_at,
                "completed_at": row.completed_at,
            },
            status=status.HTTP_200_OK,
        )

