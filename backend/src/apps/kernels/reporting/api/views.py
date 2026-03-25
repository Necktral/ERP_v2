from __future__ import annotations

from rest_framework import status
from rest_framework.response import Response
from rest_framework.views import APIView

from apps.modulos.common.pagination import get_limit_offset, paginate_queryset
from apps.modulos.common.permissions import rbac_permission
from apps.modulos.iam.authentication import JWTAuthWithOrgContext

from ..exceptions import (
    DatasetExecutionError,
    DatasetNotFoundError,
    DatasetPermissionDenied,
    DatasetScopeError,
    ReportingValidationError,
)
from ..models import ReportRun
from ..authentication import ReportingEmbedJWTAuthentication
from ..services import (
    create_run_export_from_request,
    create_saved_view_from_request,
    generate_snapshot_from_request,
    get_catalog_entry,
    get_export_detail_from_request,
    get_saved_view_detail_from_request,
    list_catalog,
    list_saved_views_from_request,
    list_snapshots_from_request,
    run_dataset_from_request,
)
from .filters import sanitize_filters
from .serializers import (
    DatasetRunIn,
    RunExportIn,
    RunsListIn,
    SavedViewCreateIn,
    SavedViewsListIn,
    SnapshotGenerateIn,
    SnapshotsListIn,
)


class ReportingAPIView(APIView):
    authentication_classes = [ReportingEmbedJWTAuthentication, JWTAuthWithOrgContext]


class CatalogListView(ReportingAPIView):
    permission_classes = [rbac_permission("report.catalog.read")]

    def get(self, request):
        rows = [row for row in list_catalog() if row.get("is_enabled")]
        return Response({"count": len(rows), "results": rows}, status=status.HTTP_200_OK)


class CatalogDetailView(ReportingAPIView):
    permission_classes = [rbac_permission("report.catalog.read")]

    def get(self, request, dataset_key: str):
        try:
            row = get_catalog_entry(dataset_key)
        except KeyError:
            return Response({"detail": "Dataset no encontrado."}, status=status.HTTP_404_NOT_FOUND)
        return Response(row, status=status.HTTP_200_OK)


class DatasetRunView(ReportingAPIView):
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
        body["quality_status"] = str(body.get("quality_status") or "")
        body["quality_checks"] = list(body.get("quality_checks") or [])
        return Response(body, status=status.HTTP_200_OK)


class RunsListView(ReportingAPIView):
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
                "quality_status": row.quality_status,
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


class RunDetailView(ReportingAPIView):
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
                "quality_status": row.quality_status,
                "quality_checks": list(row.quality_checks_json or []),
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


class RunExportCreateView(ReportingAPIView):
    permission_classes = [rbac_permission("report.dataset.export")]

    def post(self, request, run_id):
        serializer = RunExportIn(data=request.data)
        serializer.is_valid(raise_exception=True)
        payload = serializer.validated_data
        try:
            body = create_run_export_from_request(
                request=request,
                run_id=run_id,
                export_format=str(payload["format"]),
            )
        except KeyError:
            return Response({"detail": "Run no encontrado."}, status=status.HTTP_404_NOT_FOUND)
        except ReportingValidationError as exc:
            return Response({"detail": str(exc)}, status=status.HTTP_400_BAD_REQUEST)
        return Response(body, status=status.HTTP_200_OK)


class ExportDetailView(ReportingAPIView):
    permission_classes = [rbac_permission("report.dataset.export")]

    def get(self, request, export_id):
        try:
            body = get_export_detail_from_request(request=request, export_id=export_id)
        except KeyError:
            return Response({"detail": "Export no encontrado."}, status=status.HTTP_404_NOT_FOUND)
        return Response(body, status=status.HTTP_200_OK)


class SnapshotsListView(ReportingAPIView):
    permission_classes = [rbac_permission("report.run.read")]

    def get(self, request):
        serializer = SnapshotsListIn(data=request.query_params)
        serializer.is_valid(raise_exception=True)
        dataset_key = str(serializer.validated_data.get("dataset_key") or "")
        snapshot_status = str(serializer.validated_data.get("status") or "")
        qs = list_snapshots_from_request(request=request, dataset_key=dataset_key, status=snapshot_status)
        limit, offset = get_limit_offset(request)
        total, rows = paginate_queryset(qs, limit=limit, offset=offset)
        results = [
            {
                "snapshot_id": int(row.id),
                "dataset_key": row.dataset_key,
                "status": row.status,
                "fresh_until": row.fresh_until,
                "row_count": int(row.row_count or 0),
                "payload_hash": row.payload_hash,
                "schema_version": row.schema_version,
                "semantic_version": row.semantic_version,
                "company_id": getattr(row.company, "id", None),
                "branch_id": getattr(row.branch, "id", None),
                "created_at": row.created_at,
                "updated_at": row.updated_at,
            }
            for row in rows
        ]
        return Response(
            {"count": int(total), "limit": int(limit), "offset": int(offset), "results": results},
            status=status.HTTP_200_OK,
        )


class SnapshotGenerateView(ReportingAPIView):
    permission_classes = [rbac_permission("report.snapshot.generate")]

    def post(self, request):
        serializer = SnapshotGenerateIn(data=request.data)
        serializer.is_valid(raise_exception=True)
        payload = serializer.validated_data
        try:
            out = generate_snapshot_from_request(
                request=request,
                dataset_key=str(payload["dataset_key"]),
                filters=sanitize_filters(payload.get("filters")),
                force_refresh=bool(payload.get("force_refresh")),
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
        return Response(out, status=status.HTTP_200_OK)


class SavedViewsListCreateView(ReportingAPIView):
    permission_classes = []

    def get_permissions(self):
        if self.request.method == "POST":
            return [rbac_permission("report.dashboard.compose")()]
        return [rbac_permission("report.dashboard.read")()]

    def get(self, request):
        serializer = SavedViewsListIn(data=request.query_params)
        serializer.is_valid(raise_exception=True)
        try:
            qs = list_saved_views_from_request(
                request=request,
                dataset_key=str(serializer.validated_data.get("dataset_key") or ""),
            )
        except DatasetScopeError as exc:
            return Response({"detail": str(exc)}, status=status.HTTP_400_BAD_REQUEST)

        limit, offset = get_limit_offset(request)
        total, rows = paginate_queryset(qs, limit=limit, offset=offset)
        results = [
            {
                "view_id": str(row.view_id),
                "name": row.name,
                "dataset_key": row.dataset_key,
                "filters": dict(row.filters_json or {}),
                "render_state": dict(row.render_state_json or {}),
                "is_shared": bool(row.is_shared),
                "is_owner": bool(
                    getattr(request.user, "is_authenticated", False)
                    and getattr(row.requested_by, "id", None) == getattr(request.user, "id", None)
                ),
                "created_at": row.created_at,
                "updated_at": row.updated_at,
            }
            for row in rows
        ]
        return Response(
            {"count": int(total), "limit": int(limit), "offset": int(offset), "results": results},
            status=status.HTTP_200_OK,
        )

    def post(self, request):
        serializer = SavedViewCreateIn(data=request.data)
        serializer.is_valid(raise_exception=True)
        payload = serializer.validated_data
        try:
            out = create_saved_view_from_request(
                request=request,
                name=str(payload["name"]),
                dataset_key=str(payload["dataset_key"]),
                filters=sanitize_filters(payload.get("filters")),
                render_state=dict(payload.get("render_state") or {}),
                is_shared=bool(payload.get("is_shared")),
            )
        except DatasetPermissionDenied as exc:
            return Response({"detail": str(exc)}, status=status.HTTP_403_FORBIDDEN)
        except DatasetNotFoundError as exc:
            return Response({"detail": str(exc)}, status=status.HTTP_400_BAD_REQUEST)
        except (ReportingValidationError, DatasetScopeError) as exc:
            return Response({"detail": str(exc)}, status=status.HTTP_400_BAD_REQUEST)
        return Response(out, status=status.HTTP_201_CREATED)


class SavedViewDetailView(ReportingAPIView):
    permission_classes = [rbac_permission("report.dashboard.read")]

    def get(self, request, view_id):
        try:
            out = get_saved_view_detail_from_request(request=request, view_id=view_id)
        except KeyError:
            return Response({"detail": "Saved view no encontrada."}, status=status.HTTP_404_NOT_FOUND)
        except DatasetScopeError as exc:
            return Response({"detail": str(exc)}, status=status.HTTP_400_BAD_REQUEST)
        return Response(out, status=status.HTTP_200_OK)
