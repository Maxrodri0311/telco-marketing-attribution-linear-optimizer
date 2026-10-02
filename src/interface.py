"""
src/interface.py - FastAPI Microservice & Swagger (EXPLAINABLE_AI_INFERENCE Paradigm).
Inference and explainability service for vonage_marketing_data_scientist_bridge_project.
"""

from fastapi import FastAPI
from pydantic import BaseModel
from src.core_engine import create_engine

app = FastAPI(
    title="VONAGE_MARKETING_DATA_SCIENTIST_BRIDGE_PROJECT - Explainability API",
    description="Vonage requires an enterprise-grade Causal & Survival Lifecycle Analytics architecture under Marketing Data Scientist to solve operational latency, re",
    version="1.0.0",
)

@app.get("/health")
def health_check():
    return {"status": "healthy", "service": "vonage-attribution-optimizer", "version": "1.0.0"}

@app.get("/metrics/summary")
def get_metrics_summary():
    engine = create_engine()
    df = engine.execute_analysis()
    return df.to_dict(orient="records")

if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="127.0.0.1", port=8000)