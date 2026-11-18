# ============================================================
# IMPORT
# ============================================================
import logging
import os
import pickle

from fastapi import FastAPI, HTTPException, Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from pydantic import BaseModel, Field, field_validator

# ============================================================
# CONFIGURAZIONE 
# ============================================================
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("sentiment-api")

MODEL_PATH = os.getenv("MODEL_PATH", "model/sentiment_analysis_model.pkl")


def load_model(path: str):
    with open(path, "rb") as f:
        return pickle.load(f)


def predict_sentiment(model, text: str) -> tuple[str, float]:
    label = model.predict([text])[0]
    confidence = float(model.predict_proba([text]).max())
    return str(label), round(confidence, 4)


# ============================================================
# SCHEMI PYDANTIC 
# ============================================================
class ReviewRequest(BaseModel):
    review: str = Field(..., max_length=5000, examples=["This product is amazing! I love it."])

    @field_validator("review")
    @classmethod
    def not_blank(cls, v: str) -> str:
        v = v.strip()
        if not v:
            raise ValueError("La recensione non può essere vuota")
        return v


class PredictionResponse(BaseModel):
    sentiment: str
    confidence: float


# ============================================================
# CARICAMENTO MODELLO (una volta, all'avvio)
# ============================================================
model = load_model(MODEL_PATH)
logger.info("Modello caricato da %s", MODEL_PATH)

# ============================================================
# APP FASTAPI
# ============================================================
app = FastAPI(title="Sentiment Analysis API", version="1.0.0")


# ============================================================
# EXCEPTION HANDLER
# ============================================================
@app.exception_handler(RequestValidationError)
async def validation_handler(request: Request, exc: RequestValidationError):
    details = [
        {"field": ".".join(str(p) for p in e["loc"][1:]), "message": e["msg"]}
        for e in exc.errors()
    ]
    return JSONResponse(status_code=422, content={"error": "Input non valido", "details": details})


# ============================================================
# ENDPOINT
# ============================================================
@app.get("/health")
def health():
    return {"status": "ok", "model_loaded": model is not None}


@app.post("/predict", response_model=PredictionResponse)
def predict(req: ReviewRequest):
    try:
        sentiment, confidence = predict_sentiment(model, req.review)
    except Exception:
        logger.exception("Errore durante la predizione")
        raise HTTPException(status_code=500, detail="Errore durante la predizione")
    return PredictionResponse(sentiment=sentiment, confidence=confidence)