from __future__ import annotations

import re
import uuid


_REQUEST_ID_RE = re.compile(r"^[A-Za-z0-9._:-]{1,128}$")


class RequestIdMiddleware:
    """Genera/propaga X-Request-Id y lo expone en request.request_id.

    Contrato:
    - Si el cliente envía X-Request-Id válido, se respeta.
    - Si no existe o es inválido, se genera uno.
    - Siempre se devuelve X-Request-Id en la respuesta.
    """

    header_name = "X-Request-Id"

    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        incoming = request.headers.get(self.header_name)
        if incoming and _REQUEST_ID_RE.match(incoming):
            request_id = incoming
        else:
            request_id = uuid.uuid4().hex

        setattr(request, "request_id", request_id)

        response = self.get_response(request)

        try:
            response[self.header_name] = request_id
        except Exception:
            pass

        return response
