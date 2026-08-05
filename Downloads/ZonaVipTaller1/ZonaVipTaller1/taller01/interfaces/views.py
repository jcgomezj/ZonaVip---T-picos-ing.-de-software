

import json

from django.http import JsonResponse
from django.views import View

from application.services import ReservaBoletaDTO, ReservaBoletaService
from domain.builders.boleta_builder import BoletaInvalidaError


class ReservarBoletaView(View):
    service_class = ReservaBoletaService  

    def post(self, request, *args, **kwargs):
        body = json.loads(request.body)

        datos = ReservaBoletaDTO(
            usuario_id=request.user.id,
            localidad_id=body["localidad_id"],
            evento_id=body["evento_id"],
        )

        try:
            boleta = self.service_class().ejecutar(datos)
        except BoletaInvalidaError as error:
            return JsonResponse({"error": str(error)}, status=400)

        return JsonResponse(
            {
                "id": boleta.id,
                "codigo_qr": boleta.codigo_qr,
                "estado": boleta.estado,
                "precio": str(boleta.precio),
            },
            status=201,
        )
