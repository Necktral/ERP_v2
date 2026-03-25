from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response
from rest_framework.views import APIView

from apps.kernels.reporting.observability import build_reporting_observability
from apps.modulos.dashboard.observability import build_dashboard_observability

from config.metrics import snapshot
from django.conf import settings


class MetricsView(APIView):
	permission_classes = [IsAuthenticated]
	throttle_scope = "heavy_reads"

	def get(self, request):
		user = request.user
		if not getattr(user, "is_staff", False) and not getattr(user, "is_superuser", False):
			return Response({"detail": "No autorizado."}, status=403)
		base = snapshot()
		window_hours = int(getattr(settings, "REPORTING_OBSERVABILITY_WINDOW_HOURS", 24) or 24)
		base["reporting"] = build_reporting_observability(window_hours=window_hours)
		base["dashboard"] = build_dashboard_observability(window_hours=window_hours)
		return Response(base, status=200)
