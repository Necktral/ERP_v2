from __future__ import annotations

from django.urls import path

from .views import (
    CashMovementCreateView,
    CashReopenApproveView,
    CashSessionCloseView,
    CashSessionDetailView,
    CashSessionDenominationView,
    CashSessionListView,
    CashSessionOpenView,
    CashSessionReopenView,
    HealthView,
    PaymentIntentAuthorizeView,
    PaymentIntentCancelView,
    PaymentIntentCaptureView,
    PaymentIntentDetailView,
    PaymentIntentListCreateView,
    PaymentIntentRefundView,
    PaymentIntentReverseCaptureView,
    PaymentRefundApproveView,
)


urlpatterns = [
    path("health/", HealthView.as_view()),
    # PaymentIntents
    path("intents/", PaymentIntentListCreateView.as_view()),
    path("intents/<uuid:payment_id>/", PaymentIntentDetailView.as_view()),
    path("intents/<uuid:payment_id>/authorize/", PaymentIntentAuthorizeView.as_view()),
    path("intents/<uuid:payment_id>/capture/", PaymentIntentCaptureView.as_view()),
    # Refund con SoD: refund/ = maker (crea ApprovalRequest); approve = checker (ejecuta)
    path("intents/<uuid:payment_id>/refund/", PaymentIntentRefundView.as_view()),
    path("intents/<uuid:payment_id>/cancel/", PaymentIntentCancelView.as_view()),
    path("intents/<uuid:payment_id>/reverse-capture/", PaymentIntentReverseCaptureView.as_view()),
    # CashSessions
    path("cash-sessions/", CashSessionListView.as_view()),
    path("cash-sessions/open/", CashSessionOpenView.as_view()),
    path("cash-sessions/<int:session_id>/", CashSessionDetailView.as_view()),
    path("cash-sessions/<int:session_id>/close/", CashSessionCloseView.as_view()),
    # Reopen con SoD: reopen/ = maker (crea ApprovalRequest); approve = checker (ejecuta)
    path("cash-sessions/<int:session_id>/reopen/", CashSessionReopenView.as_view()),
    path("cash-sessions/<int:session_id>/denomination/", CashSessionDenominationView.as_view()),
    # GET=list, POST=create (backward compat con tests existentes)
    path("cash-sessions/<int:session_id>/movements/", CashMovementCreateView.as_view()),
    # SoD checkers (aprobación maker-checker)
    path("approvals/<uuid:request_id>/refund/approve/", PaymentRefundApproveView.as_view()),
    path("approvals/<uuid:request_id>/reopen/approve/", CashReopenApproveView.as_view()),
]
