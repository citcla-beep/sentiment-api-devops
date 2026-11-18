import pytest
from prometheus_client import REGISTRY

import app.main as main


def test_health(client):
    r = client.get("/health")
    assert r.status_code == 200
    assert r.json() == {"status": "ok", "model_loaded": True}


def test_predict_formato_risposta(client):
    r = client.post("/predict", json={"review": "This product is amazing! I love it."})
    assert r.status_code == 200
    body = r.json()
    assert set(body) == {"sentiment", "confidence"}
    assert body["sentiment"] in {"positive", "negative", "neutral"}
    assert 0.0 <= body["confidence"] <= 1.0


@pytest.mark.parametrize("testo, atteso", [
    ("This product is amazing! I love it.", "positive"),
    ("Terrible, a total waste of money", "negative"),
    ("It was okay, nothing special", "neutral"),
])
def test_predict_sentiment_atteso(client, testo, atteso):
    r = client.post("/predict", json={"review": testo})
    assert r.json()["sentiment"] == atteso


@pytest.mark.parametrize("payload", [
    {"review": ""},
    {"review": "   "},
    {},
    {"testo": "campo sbagliato"},
    {"review": 123},
])
def test_predict_input_non_valido(client, payload):
    r = client.post("/predict", json=payload)
    assert r.status_code == 422
    body = r.json()
    assert body["error"] == "Input non valido"
    assert body["details"][0]["field"] == "review"


def test_predict_json_malformato(client):
    r = client.post("/predict", content="non json", headers={"Content-Type": "application/json"})
    assert r.status_code == 422


def test_metrics_esposte(client):
    client.post("/predict", json={"review": "Great product"})
    r = client.get("/metrics")
    assert r.status_code == 200
    assert "text/plain" in r.headers["content-type"]
    for nome in ["http_requests_total", "http_request_duration_seconds",
                 "predictions_total", "prediction_errors_total"]:
        assert nome in r.text


def test_contatore_richieste_incrementa(client):
    labels = {"method": "POST", "endpoint": "/predict", "status_code": "200"}
    prima = REGISTRY.get_sample_value("http_requests_total", labels) or 0
    client.post("/predict", json={"review": "Great product"})
    assert REGISTRY.get_sample_value("http_requests_total", labels) == prima + 1


def test_errore_modello_restituisce_500_e_conta_errore(client, monkeypatch):
    class BrokenModel:
        def predict(self, X):
            raise RuntimeError("modello rotto")

    monkeypatch.setattr(main, "model", BrokenModel())
    prima = REGISTRY.get_sample_value("prediction_errors_total") or 0

    r = client.post("/predict", json={"review": "Great product"})

    assert r.status_code == 500
    assert r.json() == {"detail": "Errore durante la predizione"}
    assert REGISTRY.get_sample_value("prediction_errors_total") == prima + 1