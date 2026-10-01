FROM python:3.12-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1

WORKDIR /app

COPY pyproject.toml ./
COPY common ./common
COPY iot_diagnosis ./iot_diagnosis
COPY iot_control ./iot_control
COPY iot_mcp ./iot_mcp
COPY knowledge ./knowledge
COPY evals ./evals
COPY scripts ./scripts
COPY --from=retrieval / /opt/retrieval

RUN pip install --no-cache-dir /opt/retrieval . \
    && addgroup --system xiaoyi \
    && adduser --system --ingroup xiaoyi xiaoyi \
    && mkdir -p /app/data \
    && chown -R xiaoyi:xiaoyi /app/data

USER xiaoyi

VOLUME ["/app/data"]
