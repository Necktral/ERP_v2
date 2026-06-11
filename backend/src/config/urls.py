"""
URL configuration for config project.

The `urlpatterns` list routes URLs to views. For more information please see:
    https://docs.djangoproject.com/en/5.2/topics/http/urls/
Examples:
Function views
    1. Add an import:  from my_app import views
    2. Add a URL to urlpatterns:  path('', views.home, name='home')
Class-based views
    1. Add an import:  from other_app.views import Home
    2. Add a URL to urlpatterns:  path('', Home.as_view(), name='home')
Including another URLconf
    1. Import the include() function: from django.urls import include, path
    2. Add a URL to urlpatterns:  path('blog/', include('blog.urls'))
"""

from django.contrib import admin
from django.urls import URLPattern, URLResolver, include, path
from config.csp_report import csp_report
from drf_spectacular.views import SpectacularAPIView, SpectacularRedocView, SpectacularSwaggerView
from rest_framework.permissions import AllowAny

api_v1_urlpatterns: list[URLPattern | URLResolver] = [
    # OpenAPI
    path("schema/", SpectacularAPIView.as_view(permission_classes=[AllowAny]), name="schema-v1"),
    path("schema/swagger-ui/", SpectacularSwaggerView.as_view(url_name="schema-v1"), name="swagger-ui-v1"),
    path("schema/redoc/", SpectacularRedocView.as_view(url_name="schema-v1"), name="redoc-v1"),
    # CSP reports (report-only)
    path("csp/report/", csp_report, name="csp-report-v1"),
    # Auth / platform
    path("auth/", include("apps.modulos.accounts.urls")),
    path("iam/", include("apps.modulos.iam.urls")),
    path("rbac/", include("apps.modulos.rbac.urls")),
    path("sync/", include("apps.modulos.sync_engine.urls")),
    path("audit/", include("apps.modulos.audit.urls")),
    path("metrics/", include("apps.modulos.common.urls")),
    path("org/", include("apps.modulos.org.urls")),
    path("hr/", include("apps.modulos.hr.urls")),
    # Business domains
    path("accounting/", include("apps.kernels.accounting.urls")),
    path("payments/", include("apps.kernels.payments.urls")),
    path("portfolio/", include("apps.kernels.portfolio.urls", namespace="portfolio-v1")),
    path("reporting/", include("apps.kernels.reporting.urls")),
    path("backend/dashboard/", include("apps.modulos.dashboard.urls")),
    path("cec/", include("apps.modulos.cec.urls")),
    path("integration/", include("apps.modulos.integration.urls")),
    path("fuel/", include("apps.modulos.estacion_servicios.urls")),
    path("retail/pos/", include("apps.modulos.retail_pos.urls")),
    path("inventory/", include("apps.kernels.inventarios.urls")),
    path("billing/", include("apps.kernels.facturacion.urls")),
    path("nomina/", include("apps.kernels.nomina.urls")),
    path("procurement/", include("apps.modulos.compras.urls")),
]

urlpatterns = [
    path("admin/", admin.site.urls),
    path("api/v1/", include(api_v1_urlpatterns)),
    # OpenAPI
    path("api/schema/", SpectacularAPIView.as_view(permission_classes=[AllowAny]), name="schema"),
    path("api/schema/swagger-ui/", SpectacularSwaggerView.as_view(url_name="schema"), name="swagger-ui"),
    path("api/schema/redoc/", SpectacularRedocView.as_view(url_name="schema"), name="redoc"),
    # CSP reports (report-only)
    path("api/csp/report/", csp_report, name="csp-report"),
    # Auth
    path("api/auth/", include("apps.modulos.accounts.urls")),
    # IAM
    path("api/iam/", include("apps.modulos.iam.urls")),
    # RBAC
    path("api/rbac/", include("apps.modulos.rbac.urls")),
    path("api/sync/", include("apps.modulos.sync_engine.urls")),
    # Auditoría
    path("api/audit/", include("apps.modulos.audit.urls")),
    # Observabilidad
    path("api/metrics/", include("apps.modulos.common.urls")),
    # ORG
    path("api/org/", include("apps.modulos.org.urls")),
    # HR
    path("api/hr/", include("apps.modulos.hr.urls")),
    # Controls (Capa 3: anti-fraude / SoD / hallazgos)
    path("api/controls/", include("apps.modulos.controls.urls")),
    # Manejo de Fincas (agrícola)
    path("api/finca/", include("apps.modulos.finca.urls")),
    # Accounting
    path("api/accounting/", include("apps.kernels.accounting.urls")),
    # Intercompany (operaciones entre empresas del grupo + posición consolidada)
    path("api/intercompany/", include("apps.modulos.intercompany.urls")),
    # Payments/Cash
    path("api/payments/", include("apps.kernels.payments.urls")),
    # Portfolio (CxC, CxP, Credits)
    path("api/portfolio/", include("apps.kernels.portfolio.urls")),
    # Reporting kernel
    path("api/reporting/", include("apps.kernels.reporting.urls")),
    # Dashboard gateway (embed + workspaces)
    path("api/backend/dashboard/", include("apps.modulos.dashboard.urls")),
    # CEC
    path("api/cec/", include("apps.modulos.cec.urls")),
    # Integration Backbone
    path("api/integration/", include("apps.modulos.integration.urls")),
    # Fuel vertical canonical + legacy aliases
    path("api/fuel/", include("apps.modulos.estacion_servicios.urls")),
    path("api/backend/fuel/", include("apps.modulos.estacion_servicios.urls")),
    path("api/backend/estacion-servicios/", include("apps.modulos.estacion_servicios.urls")),
    path("api/retail/pos/", include("apps.modulos.retail_pos.urls")),
]

urlpatterns += [
    path("api/inventory/", include("apps.kernels.inventarios.urls")),
    path("api/billing/", include("apps.kernels.facturacion.urls")),
    path("api/nomina/", include("apps.kernels.nomina.urls")),
    path("api/legacy/billing/", include("apps.kernels.facturacion.urls_legacy")),
    path("api/procurement/", include("apps.modulos.compras.urls")),
    path("api/comisariato/", include("apps.modulos.comisariato.urls")),
    path("api/fleet/", include("apps.modulos.fleet.urls")),
    path("api/notifications/", include("apps.modulos.notifications.urls")),
    path("api/documents/", include("apps.modulos.documents.urls")),
    path("api/diagnostics/", include("apps.modulos.diagnostics.urls")),
    path("api/knowledge/", include("apps.modulos.knowledge.urls")),
]
