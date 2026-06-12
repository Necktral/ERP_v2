from __future__ import annotations

from django.core.exceptions import ValidationError as DjangoValidationError
from django.db.models import Prefetch, Q
from django.shortcuts import get_object_or_404
from rest_framework import status
from rest_framework.exceptions import ValidationError
from rest_framework.response import Response
from rest_framework.views import APIView

from apps.modulos.common.pagination import get_limit_offset, paginate_queryset
from apps.modulos.common.permissions import rbac_permission
from apps.modulos.common.throttling import MethodThrottleScopeMixin

from .models import Party, PartyRole
from .serializers import PartyCreateIn, PartyRoleActionIn, PartyUpdateIn, party_out
from .services import assign_party_role, create_party, revoke_party_role, update_party


def _raise_drf(exc: DjangoValidationError):
    """Convierte ValidationError de Django al de DRF (el envelope lo mapea a 422)."""
    detail = getattr(exc, "message_dict", None) or {"detail": exc.messages}
    raise ValidationError(detail)


def _scoped_party(request, party_id: int) -> Party:
    return get_object_or_404(Party, id=party_id, company=request.company)


class PartyListCreateView(MethodThrottleScopeMixin, APIView):
    """Directorio de terceros de la empresa activa.

    GET  -> parties.party.read   (filtros: q, role, status, party_type)
    POST -> parties.party.create (opcionalmente con roles iniciales)
    """

    throttle_scope_by_method = {
        "GET": "heavy_reads",
        "POST": "admin_writes",
    }

    def get_permissions(self):
        if self.request.method == "POST":
            return [rbac_permission("parties.party.create")()]
        return [rbac_permission("parties.party.read")()]

    def get(self, request):
        qs = (
            Party.objects.filter(company=request.company)
            .prefetch_related(
                Prefetch("roles", queryset=PartyRole.objects.filter(is_active=True))
            )
            .order_by("display_name")
        )
        q = (request.query_params.get("q") or "").strip()
        if q:
            qs = qs.filter(
                Q(display_name__icontains=q)
                | Q(legal_name__icontains=q)
                | Q(tax_id__icontains=q.upper())
                | Q(national_id__icontains=q.upper())
            )
        role = (request.query_params.get("role") or "").strip().upper()
        if role:
            qs = qs.filter(roles__role=role, roles__is_active=True)
        status_filter = (request.query_params.get("status") or "").strip().upper()
        if status_filter:
            qs = qs.filter(status=status_filter)
        party_type = (request.query_params.get("party_type") or "").strip().upper()
        if party_type:
            qs = qs.filter(party_type=party_type)

        limit, offset = get_limit_offset(request)
        total, rows = paginate_queryset(qs.distinct(), limit=limit, offset=offset)
        return Response(
            {
                "count": total,
                "limit": limit,
                "offset": offset,
                "results": [party_out(p) for p in rows],
            },
            status=status.HTTP_200_OK,
        )

    def post(self, request):
        s = PartyCreateIn(data=request.data)
        s.is_valid(raise_exception=True)
        v = s.validated_data
        roles = v.pop("roles", [])
        try:
            party = create_party(company=request.company, request=request, actor=request.user, **v)
            for role in dict.fromkeys(roles):  # únicos, en orden
                assign_party_role(party=party, role=role, request=request, actor=request.user)
        except DjangoValidationError as exc:
            _raise_drf(exc)
        return Response(party_out(party, active_roles=list(roles)), status=status.HTTP_201_CREATED)


class PartyDetailView(MethodThrottleScopeMixin, APIView):
    """GET -> parties.party.read ; PATCH -> parties.party.update."""

    throttle_scope_by_method = {
        "GET": "heavy_reads",
        "PATCH": "admin_writes",
    }

    def get_permissions(self):
        if self.request.method == "PATCH":
            return [rbac_permission("parties.party.update")()]
        return [rbac_permission("parties.party.read")()]

    def get(self, request, party_id: int):
        party = _scoped_party(request, party_id)
        return Response(party_out(party), status=status.HTTP_200_OK)

    def patch(self, request, party_id: int):
        party = _scoped_party(request, party_id)
        s = PartyUpdateIn(data=request.data, partial=True)
        s.is_valid(raise_exception=True)
        if not s.validated_data:
            raise ValidationError({"detail": "Nada que actualizar."})
        try:
            party = update_party(party=party, request=request, actor=request.user, **s.validated_data)
        except DjangoValidationError as exc:
            _raise_drf(exc)
        return Response(party_out(party), status=status.HTTP_200_OK)


class PartyRoleAssignView(APIView):
    """POST {role} -> asigna un rol activo al tercero."""

    permission_classes = [rbac_permission("parties.role.manage")]
    throttle_scope = "admin_writes"

    def post(self, request, party_id: int):
        party = _scoped_party(request, party_id)
        s = PartyRoleActionIn(data=request.data)
        s.is_valid(raise_exception=True)
        try:
            assign_party_role(party=party, role=s.validated_data["role"], request=request, actor=request.user)
        except DjangoValidationError as exc:
            _raise_drf(exc)
        return Response(party_out(party), status=status.HTTP_200_OK)


class PartyRoleRevokeView(APIView):
    """POST {role} -> revoca el rol activo del tercero."""

    permission_classes = [rbac_permission("parties.role.manage")]
    throttle_scope = "admin_writes"

    def post(self, request, party_id: int):
        party = _scoped_party(request, party_id)
        s = PartyRoleActionIn(data=request.data)
        s.is_valid(raise_exception=True)
        try:
            revoke_party_role(party=party, role=s.validated_data["role"], request=request, actor=request.user)
        except DjangoValidationError as exc:
            _raise_drf(exc)
        return Response(party_out(party), status=status.HTTP_200_OK)
