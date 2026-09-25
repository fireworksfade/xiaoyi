FROM python:3.12-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1

WORKDIR /app

COPY pyproject.toml README.md ./
COPY common ./common
COPY iot_diagnosis ./iot_diagnosis
COPY iot_control ./iot_control
COPY knowledge ./knowledge
COPY evals ./evals
COPY scripts ./scripts

RUN pip install --no-cache-dir . \
    && addgroup --system xiaoyi \
    && adduser --system --ingroup xiaoyi xiaoyi \
    && mkdir -p /app/data \
    && chown -R xiaoyi:xiaoyi /app/data

USER xiaoyi

VOLUME ["/app/data"]
