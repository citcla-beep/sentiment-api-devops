import numpy as np
import pytest
from pydantic import ValidationError

from app.main import MODEL_PATH, ReviewRequest, load_model, predict_sentiment


@pytest.fixture(scope="module")      # caricato una volta per tutto il file
def model():
    return load_model(MODEL_PATH)


# --- Validazione input ---
def test_review_valida():
    assert ReviewRequest(review="Great product").review == "Great product"


def test_review_strip_spazi():
    assert ReviewRequest(review="  Great product  ").review == "Great product"


@pytest.mark.parametrize("testo", ["", "   ", "\n\t"])
def test_review_vuota_rifiutata(testo):
    with pytest.raises(ValidationError):
        ReviewRequest(review=testo)


def test_review_troppo_lunga_rifiutata():
    with pytest.raises(ValidationError):
        ReviewRequest(review="a" * 5001)


# --- Modello ---
def test_modello_ha_tre_classi(model):
    assert list(model.classes_) == ["negative", "neutral", "positive"]


@pytest.mark.parametrize("testo, atteso", [
    ("This product is amazing! I love it.", "positive"),
    ("Terrible, a total waste of money", "negative"),
    ("It was okay, nothing special", "neutral"),
])
def test_predizioni_note(model, testo, atteso):
    sentiment, _ = predict_sentiment(model, testo)
    assert sentiment == atteso


def test_confidence_tra_0_e_1(model):
    _, confidence = predict_sentiment(model, "Great product")
    assert isinstance(confidence, float)
    assert 0.0 <= confidence <= 1.0


# --- Logica isolata dal modello reale ---
def test_predict_sentiment_con_modello_finto():
    class FakeModel:
        def predict(self, X):
            return np.array(["positive"])

        def predict_proba(self, X):
            return np.array([[0.1, 0.2, 0.7]])

    assert predict_sentiment(FakeModel(), "qualsiasi testo") == ("positive", 0.7)