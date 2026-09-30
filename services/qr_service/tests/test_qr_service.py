"""
Pruebas del microservicio de QR.

Cubren el dominio puro (`qr_engine`) y el contrato HTTP/JSON de la API
(incluyendo el manejo estructurado de errores 400/404/405), en la misma
disciplina de testing del monolito.

Ejecutar (desde services/qr_service/):
    pip install -r requirements.txt pytest
    pytest
"""

import pytest

from app import crear_app
from domain.qr_engine import (
    QRDominioError,
    construir_payload,
    generar_qr,
    validar_qr,
)


@pytest.fixture
def client():
    app = crear_app()
    app.config.update(TESTING=True)
    return app.test_client()


# --------------------------------------------------------------------------
# Dominio puro
# --------------------------------------------------------------------------


def test_generar_qr_devuelve_imagen_base64():
    resultado = generar_qr(1, "codigo-abc")
    assert resultado["imagen_base64"].startswith("data:image/png;base64,")
    assert resultado["boleta_id"] == 1
    assert resultado["formato"] == "PNG"


def test_payload_firmado_es_valido():
    payload = construir_payload(42, "uuid-xyz")
    resultado = validar_qr(payload)
    assert resultado["valido"] is True
    assert resultado["boleta_id"] == 42


def test_qr_manipulado_es_invalido():
    payload = construir_payload(42, "uuid-xyz")
    manipulado = payload.replace("uuid-xyz", "uuid-hackeado")
    resultado = validar_qr(manipulado)
    assert resultado["valido"] is False


def test_boleta_id_invalido_lanza_error():
    with pytest.raises(QRDominioError):
        construir_payload(0, "codigo")


# --------------------------------------------------------------------------
# Contrato HTTP / JSON
# --------------------------------------------------------------------------


def test_health_ok(client):
    resp = client.get("/api/v2/qr/health")
    assert resp.status_code == 200
    assert resp.get_json()["estado"] == "ok"


def test_generar_endpoint_201(client):
    resp = client.post("/api/v2/qr/generar", json={"boleta_id": 7})
    assert resp.status_code == 201
    body = resp.get_json()
    assert body["boleta_id"] == 7
    assert "imagen_base64" in body


def test_generar_sin_boleta_id_devuelve_400(client):
    resp = client.post("/api/v2/qr/generar", json={})
    assert resp.status_code == 400
    assert resp.get_json()["tipo"] == "validacion_negocio"


def test_validar_endpoint_flujo_completo(client):
    gen = client.post(
        "/api/v2/qr/generar", json={"boleta_id": 9, "codigo_qr": "abc"}
    ).get_json()
    resp = client.post("/api/v2/qr/validar", json={"payload": gen["payload"]})
    assert resp.status_code == 200
    assert resp.get_json()["valido"] is True


def test_ruta_inexistente_devuelve_404_json(client):
    resp = client.get("/api/v2/qr/no-existe")
    assert resp.status_code == 404
    assert resp.get_json()["tipo"] == "not_found"


def test_metodo_no_permitido_devuelve_405_json(client):
    resp = client.get("/api/v2/qr/generar")
    assert resp.status_code == 405
    assert resp.get_json()["tipo"] == "method_not_allowed"
