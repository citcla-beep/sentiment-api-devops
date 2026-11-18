# ============================================================
# IMPORT
# ============================================================
import logging
import os
import pickle
import time

from fastapi import FastAPI, HTTPException, Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse, Response  
from prometheus_client import CONTENT_TYPE_LATEST, Counter, Histogram, generate_latest
from pydantic import BaseModel, Field, field_validator

# ============================================================
# CONFIGURAZIONE 
# ============================================================
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("sentiment-api")

MODEL_PATH = os.getenv("MODEL_PATH", "model/sentiment_analysis_model.pkl")

REQUEST_COUNT = Counter(
    "http_requests_total", "Totale richieste HTTP",
    ["method", "endpoint", "status_code"],
)
REQUEST_LATENCY = Histogram(
    "http_request_duration_seconds", "Durata richieste HTTP",
    ["method", "endpoint"],
    buckets=(0.005, 0.01, 0.025, 0.05, 0.1, 0.25, 0.5, 1, 2.5),
)
PREDICTIONS = Counter("predictions_total", "Predizioni per sentiment", ["sentiment"])
PREDICTION_ERRORS = Counter("prediction_errors_total", "Errori durante la predizione")
PREDICTION_CONFIDENCE = Histogram(
    "prediction_confidence", "Distribuzione della confidence",
    buckets=(0.4, 0.5, 0.6, 0.7, 0.8, 0.9, 1.0),
)

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

@app.middleware("http")
async def metrics_middleware(request: Request, call_next):
    if request.url.path == "/metrics":           # non misurare lo scraping stesso
        return await call_next(request)
    start = time.perf_counter()
    status_code = 500                            # default se esplode un'eccezione
    try:
        response = await call_next(request)
        status_code = response.status_code
        return response
    finally:
        route = request.scope.get("route")
        endpoint = route.path if route else "unmatched"
        REQUEST_LATENCY.labels(request.method, endpoint).observe(time.perf_counter() - start)
        REQUEST_COUNT.labels(request.method, endpoint, str(status_code)).inc()
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
        PREDICTION_ERRORS.inc()
        logger.exception("Errore durante la predizione")
        raise HTTPException(status_code=500, detail="Errore durante la predizione")
    PREDICTIONS.labels(sentiment).inc()
    PREDICTION_CONFIDENCE.observe(confidence)
    return PredictionResponse(sentiment=sentiment, confidence=confidence)

@app.get("/metrics")
def metrics():
    return Response(generate_latest(), media_type=CONTENT_TYPE_LATEST)