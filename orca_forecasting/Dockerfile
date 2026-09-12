# ORCA inference microservice image.
# Builds a slim, stateless FastAPI service that loads a pre-trained artifact
# bundle at startup and serves anomaly predictions. Training is done offline;
# this image only needs the core + service dependencies.

FROM python:3.11-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1 \
    ORCA_ARTIFACT_DIR=/artifacts

WORKDIR /app

# Install core + service (+ onnx runtime) deps only. Build tooling is not kept.
COPY requirements.txt ./
RUN pip install --upgrade pip \
    && pip install \
        "numpy>=1.24,<3.0" "pandas>=2.0,<3.0" "pyarrow>=12.0" \
        "scikit-learn>=1.3,<2.0" "joblib>=1.3" "PyYAML>=6.0" \
        "fastapi>=0.104" "uvicorn[standard]>=0.24" "pydantic>=2.0" \
        "onnxruntime>=1.16"

COPY orca ./orca
COPY service ./service
COPY configs ./configs

# Mount or COPY a trained bundle into /artifacts at deploy time.
# COPY artifacts /artifacts

EXPOSE 8000

# ORCA_ARTIFACT_DIR is read by the service at startup.
CMD ["uvicorn", "service.app:app", "--host", "0.0.0.0", "--port", "8000"]
