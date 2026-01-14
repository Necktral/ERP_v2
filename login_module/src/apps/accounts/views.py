from django.http import QueryDict
from django.contrib.auth import get_user_model
from rest_framework import status
from rest_framework.permissions import AllowAny, IsAuthenticated
from rest_framework.response import Response
from rest_framework.views import APIView
from rest_framework_simplejwt.tokens import RefreshToken
from rest_framework_simplejwt.views import TokenRefreshView

from apps.audit.writer import write_event

from apps.iam.models import AdminGrant, OrgUnit, UserMembership
from apps.iam.selectors import build_acl_snapshot
from apps.org.models import BranchProfile, CompanyProfile
from apps.rbac.models import Role, RoleAssignment
from apps.rbac.seed_v01 import seed_rbac_v01

from .serializers import (
    LoginSerializer,
    MeSerializer,
    BootstrapInitSerializer,
    BootstrapOrgSerializer,
    PasswordChangeSerializer,
)

User = get_user_model()


def _extract_login_reason_code(serializer_errors) -> str:
    # serializer_errors puede contener ErrorDetail con .code
    try:
        nfe = serializer_errors.get("non_field_errors", [])
        if nfe:
            code = getattr(nfe[0], "code", "")
            if code == "user_disabled":
                return "USER_DISABLED"
            if code == "invalid_credentials":
                return "INVALID_CREDENTIALS"
    except Exception:
        pass
    return "INVALID_CREDENTIALS"


class LoginView(APIView):
    permission_classes = [AllowAny]

    def post(self, request):
        # Axes usa request.POST para extraer el username. En JSON, request.POST viene vacío.
        qd = QueryDict("", mutable=True)
        qd.update({"username": request.data.get("username", "")})
        request._request.POST = qd  # compatibilidad Axes

        serializer = LoginSerializer(data=request.data, context={"request": request})
        if not serializer.is_valid():
            reason = _extract_login_reason_code(serializer.errors)
            write_event(
                request=request,
                event_type="AUTH_LOGIN_FAILURE",
                reason_code=reason,
                actor_user=None,
                subject_type="USER",
                subject_id=str(request.data.get("username", "")),
                metadata={"stage": "login"},
            )
            return Response(serializer.errors, status=status.HTTP_401_UNAUTHORIZED)

        user = serializer.validated_data["user"]
        refresh = RefreshToken.for_user(user)

        # Nota: must_change_password se evalúa en /me y el frontend redirige a /password-change
        # No alteramos tokens aquí.

        write_event(
            request=request,
            event_type="AUTH_LOGIN_SUCCESS",
            reason_code="",
            actor_user=user,
            subject_type="USER",
            subject_id=str(user.id),
            metadata={"username": user.username},
        )

        return Response(
            {
                "access": str(refresh.access_token),
                "refresh": str(refresh),
            },
            status=status.HTTP_200_OK,
        )


class RefreshView(TokenRefreshView):
    permission_classes = [AllowAny]

    def post(self, request, *args, **kwargs):
        response = super().post(request, *args, **kwargs)

        if response.status_code == 200:
            write_event(
                request=request,
                event_type="AUTH_TOKEN_REFRESH",
                reason_code="",
                actor_user=None,
                subject_type="SESSION",
                subject_id="",
                metadata={"stage": "refresh"},
            )
        else:
            write_event(
                request=request,
                event_type="AUTH_TOKEN_REFRESH_FAILURE",
                reason_code="TOKEN_INVALID",
                actor_user=None,
                subject_type="SESSION",
                subject_id="",
                metadata={"stage": "refresh"},
            )
        return response


class LogoutView(APIView):
    # Seguridad: evita que un tercero pueda invalidar refresh ajenos (DoS por blacklist).
    permission_classes = [IsAuthenticated]

    def post(self, request):
        refresh = request.data.get("refresh")
        if not refresh:
            write_event(
                request=request,
                event_type="AUTH_LOGOUT_FAILURE",
                reason_code="TOKEN_INVALID",
                actor_user=request.user,
                subject_type="SESSION",
                subject_id="",
                metadata={"stage": "logout", "detail": "missing_refresh"},
            )
            return Response({"detail": "refresh es requerido."}, status=status.HTTP_400_BAD_REQUEST)

        try:
            token = RefreshToken(refresh)

            token_user_id = token.get("user_id")
            if token_user_id is not None and str(token_user_id) != str(request.user.id):
                write_event(
                    request=request,
                    event_type="AUTH_LOGOUT_FAILURE",
                    reason_code="TOKEN_MISMATCH",
                    actor_user=request.user,
                    subject_type="SESSION",
                    subject_id="",
                    metadata={"stage": "logout", "detail": "refresh_owner_mismatch"},
                )
                return Response({"detail": "refresh no pertenece al usuario."}, status=status.HTTP_403_FORBIDDEN)

            token.blacklist()
        except Exception:
            write_event(
                request=request,
                event_type="AUTH_LOGOUT_FAILURE",
                reason_code="TOKEN_INVALID",
                actor_user=request.user,
                subject_type="SESSION",
                subject_id="",
                metadata={"stage": "logout", "detail": "invalid_refresh"},
            )
            return Response({"detail": "refresh inválido."}, status=status.HTTP_400_BAD_REQUEST)

        write_event(
            request=request,
            event_type="AUTH_LOGOUT",
            reason_code="",
            actor_user=request.user,
            subject_type="USER",
            subject_id=str(request.user.id),
            metadata={"stage": "logout"},
        )
        return Response(status=status.HTTP_204_NO_CONTENT)


class BootstrapStatusView(APIView):
    permission_classes = [AllowAny]

    def get(self, request):
        has_user = User.objects.exists()
        is_fresh = not has_user

        has_holding = OrgUnit.objects.filter(unit_type=OrgUnit.UnitType.HOLDING, is_active=True).exists()
        has_company = OrgUnit.objects.filter(unit_type=OrgUnit.UnitType.COMPANY, is_active=True).exists()
        setup_required = (not has_holding) or (not has_company)

        return Response(
            {"is_fresh": bool(is_fresh), "setup_required": bool(setup_required)},
            status=status.HTTP_200_OK,
        )


class BootstrapInitView(APIView):
    permission_classes = [AllowAny]

    def post(self, request):
        # contrato: solo se permite cuando no hay usuarios
        if User.objects.exists():
            return Response({"detail": "Sistema ya inicializado."}, status=status.HTTP_400_BAD_REQUEST)

        s = BootstrapInitSerializer(data=request.data)
        if not s.is_valid():
            return Response(s.errors, status=status.HTTP_400_BAD_REQUEST)
        v = s.validated_data

        user = User.objects.create_user(
            username=v["username"].strip(),
            email=(v.get("email") or None),
            password=v["password"],
            first_name=v.get("first_name", ""),
            last_name=v.get("last_name", ""),
        )
        user.is_staff = True
        user.is_superuser = True
        user.must_change_password = False
        user.save(update_fields=["is_staff", "is_superuser", "must_change_password"])

        write_event(
            request=request,
            event_type="AUTH_BOOTSTRAP_ADMIN_CREATED",
            reason_code="OK",
            actor_user=user,
            subject_type="USER",
            subject_id=str(user.id),
            metadata={"username": user.username},
        )

        return Response({"id": user.id}, status=status.HTTP_201_CREATED)


class BootstrapOrgView(APIView):
    permission_classes = [IsAuthenticated]

    def post(self, request):
        s = BootstrapOrgSerializer(data=request.data)
        if not s.is_valid():
            return Response(s.errors, status=status.HTTP_400_BAD_REQUEST)
        v = s.validated_data

        # contrato inicial: solo 1 holding en bootstrap
        if OrgUnit.objects.filter(unit_type=OrgUnit.UnitType.HOLDING, is_active=True).exists():
            return Response({"detail": "Bootstrap ya realizado."}, status=status.HTTP_409_CONFLICT)

        from django.db import transaction

        with transaction.atomic():
            # 1) Seed RBAC (idempotente)
            seed_rbac_v01()

            # 2) Holding
            holding = OrgUnit.objects.create(
                unit_type=OrgUnit.UnitType.HOLDING,
                name=v["holding_name"].strip(),
                code="",
                is_active=True,
            )

            # 3) Company
            company = OrgUnit.objects.create(
                unit_type=OrgUnit.UnitType.COMPANY,
                parent=holding,
                name=v["company_name"].strip(),
                code="",
                is_active=True,
            )

            cp, _ = CompanyProfile.objects.get_or_create(company=company)
            # Completar campos pedidos por el wizard
            cp.legal_name = v["company_name"].strip()
            cp.tax_id = (v.get("company_tax_id") or "").strip()
            cp.save(update_fields=["legal_name", "tax_id"])

            # 4) Branch inicial
            branch = OrgUnit.objects.create(
                unit_type=OrgUnit.UnitType.BRANCH,
                parent=company,
                name=v["branch_name"].strip(),
                code="",
                is_active=True,
            )

            bp, _ = BranchProfile.objects.get_or_create(branch=branch)
            bp.address = (v.get("branch_address") or "").strip()
            bp.save(update_fields=["address"])

            # 5) Membership a COMPANY (esto habilita accesibilidad en ACL snapshot)
            UserMembership.objects.get_or_create(
                user=request.user,
                org_unit=company,
                defaults={"is_active": True},
            )

            # 6) RoleAssignment SYSTEM: company_admin (scope COMPANY)
            role = Role.objects.filter(name="company_admin").first()
            if not role:
                return Response(
                    {"detail": "Falta role 'company_admin'. Ejecuta seed_rbac_v01."},
                    status=status.HTTP_500_INTERNAL_SERVER_ERROR,
                )

            RoleAssignment.objects.get_or_create(
                user=request.user,
                role=role,
                org_unit=company,
                origin=RoleAssignment.Origin.SYSTEM,
                defaults={"is_active": True, "origin_ref": "bootstrap"},
            )

            # 7) AdminGrants (scoped a COMPANY, completos)
            for cap, _ in AdminGrant.Capability.choices:
                AdminGrant.objects.get_or_create(
                    user=request.user,
                    org_unit=company,
                    capability=cap,
                    defaults={"applies_to_subtree": True, "is_active": True},
                )

        write_event(
            request=request,
            event_type="IAM_BOOTSTRAP_ORG_CREATED",
            reason_code="OK",
            actor_user=request.user,
            subject_type="COMPANY",
            subject_id=str(company.id),
            metadata={"holding_id": holding.id, "company_id": company.id, "branch_id": branch.id},
        )

        return Response(
            {"holding_id": holding.id, "company_id": company.id, "branch_id": branch.id},
            status=status.HTTP_200_OK,
        )


class PasswordChangeView(APIView):
    permission_classes = [IsAuthenticated]

    def post(self, request):
        s = PasswordChangeSerializer(data=request.data)
        if not s.is_valid():
            return Response(s.errors, status=status.HTTP_400_BAD_REQUEST)
        v = s.validated_data

        user = request.user
        if not user.check_password(v["old_password"]):
            write_event(
                request=request,
                event_type="AUTH_PASSWORD_CHANGE_FAILURE",
                reason_code="INVALID_OLD_PASSWORD",
                actor_user=user,
                subject_type="USER",
                subject_id=str(user.id),
                metadata={"stage": "password_change"},
            )
            return Response({"old_password": "Incorrecta"}, status=status.HTTP_400_BAD_REQUEST)

        user.set_password(v["new_password"])
        if hasattr(user, "must_change_password"):
            user.must_change_password = False
            user.save(update_fields=["password", "must_change_password"])
        else:
            user.save(update_fields=["password"])

        write_event(
            request=request,
            event_type="AUTH_PASSWORD_CHANGED",
            reason_code="OK",
            actor_user=user,
            subject_type="USER",
            subject_id=str(user.id),
            metadata={"stage": "password_change"},
        )

        return Response({"ok": True}, status=status.HTTP_200_OK)


class MeView(APIView):
    permission_classes = [IsAuthenticated]

    def get(self, request):
        payload = MeSerializer.from_user(request.user)
        return Response(payload, status=status.HTTP_200_OK)


# --- ACL Snapshot endpoint ---
class MeACLView(APIView):
    permission_classes = [IsAuthenticated]

    def get(self, request):
        return Response(build_acl_snapshot(request.user), status=status.HTTP_200_OK)
