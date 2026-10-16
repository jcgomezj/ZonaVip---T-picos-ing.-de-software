"""
Pruebas del microservicio de integración.

Se usan dobles de prueba (fakes) que implementan los puertos, demostrando el
valor del Patrón Adapter + Inversión de Dependencias: podemos probar la lógica
SIN llamar a ninguna API externa real.

Ejecutar (desde services/integracion_service/):
    pip install -r requirements.txt pytest
    pytest
"""

import pytest

from app import crear_app
from application.services import IntegracionService
from domain.ports import ClimaEvento, InfoAliado, ProveedorClimaPort, ServicioAliadoPort


# --- Dobles de prueba (implementan los puertos) ---------------------------


class FakeClima(ProveedorClimaPort):
    def obtener_clima(self, ciudad, lat, lon):
        return ClimaEvento(
            ciudad=ciudad,
            temperatura_c=22.5,
            descripcion="Despejado",
            es_apto_aire_libre=True,
            proveedor="FakeProvider",
        )


class FakeAliadoOk(ServicioAliadoPort):
    def obtener_info(self):
        return InfoAliado(disponible=True, datos={"equipo": "aliado"}, fuente="http://fake")


class FakeAliadoCaido(ServicioAliadoPort):
    def obtener_info(self):
        return InfoAliado(disponible=False, datos={}, fuente="http://fake", error="timeout")


# --- Dominio / aplicación --------------------------------------------------


def test_service_clima_traduce_a_dominio():
    svc = IntegracionService(FakeClima(), FakeAliadoOk())
    resultado = svc.clima_para_sede("Bogotá", 4.6, -74.0)
    assert resultado["ciudad"] == "Bogotá"
    assert resultado["es_apto_aire_libre"] is True
    assert resultado["proveedor"] == "FakeProvider"


def test_service_aliado_disponible():
    svc = IntegracionService(FakeClima(), FakeAliadoOk())
    assert svc.info_aliado()["disponible"] is True


def test_service_aliado_caido_es_resiliente():
    svc = IntegracionService(FakeClima(), FakeAliadoCaido())
    info = svc.info_aliado()
    assert info["disponible"] is False
    assert info["error"] == "timeout"


# --- Contrato HTTP ---------------------------------------------------------


@pytest.fixture
def client():
    app = crear_app()
    app.config.update(TESTING=True)
    return app.test_client()


def test_health(client):
    assert client.get("/api/v2/integracion/health").status_code == 200


def test_info_expone_json_del_sistema(client):
    resp = client.get("/api/v2/integracion/info")
    assert resp.status_code == 200
    body = resp.get_json()
    assert body["sistema"] == "ZonaVip"
    assert "microservicios" in body


def test_ruta_inexistente_404_json(client):
    resp = client.get("/api/v2/integracion/no-existe")
    assert resp.status_code == 404
    assert resp.get_json()["tipo"] == "not_found"
