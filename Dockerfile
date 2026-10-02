# ==============================================================================
# Production Multi-Stage Dockerfile for Vonage Marketing XAI Inference Microservice
# Base: python:3.11-slim | Non-Root Security | Multi-Stage Size Optimization
# ==============================================================================

# Stage 1: Build Dependencies
FROM python:3.11-slim AS builder

WORKDIR /build

RUN apt-get update && apt-get install -y --no-install-recommends \
    build-essential \
    && rm -rf /var/lib/apt/lists/*

COPY requirements.txt .
RUN pip install --no-cache-dir --user -r requirements.txt


# Stage 2: Minimal Production Runner
FROM python:3.11-slim AS runner

LABEL maintainer="Maximiliano Rodriguez <maxrodri0311@gmail.com>"
LABEL service="vonage-marketing-attribution-xai-engine"
LABEL role="Marketing Data Scientist"

WORKDIR /app

# Create unprivileged system user for zero-trust security
RUN groupadd -g 10001 nonroot && \
    useradd -u 10001 -g nonroot -s /bin/bash -m nonroot

# Copy installed python site-packages from builder
COPY --from=builder /root/.local /home/nonroot/.local
ENV PATH="/home/nonroot/.local/bin:${PATH}"
ENV PYTHONUNBUFFERED=1
ENV PYTHONDONTWRITEBYTECODE=1

# Copy application source code
COPY --chown=nonroot:nonroot src/ ./src/
COPY --chown=nonroot:nonroot analytics/ ./analytics/
COPY --chown=nonroot:nonroot pyproject.toml .

# Create data directory with write permissions for nonroot
RUN mkdir -p /app/data && chown -R nonroot:nonroot /app/data

USER nonroot

EXPOSE 8000

# Zero-dependency native HTTP healthcheck
HEALTHCHECK --interval=30s --timeout=5s --start-period=10s --retries=3 \
    CMD python -c "import http.client; conn = http.client.HTTPConnection('localhost', 8000); conn.request('GET', '/health'); res = conn.getresponse(); exit(0 if res.status == 200 else 1)"

CMD ["uvicorn", "src.interface:app", "--host", "0.0.0.0", "--port", "8000"]
