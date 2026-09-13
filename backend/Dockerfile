FROM python:3.12-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PORT=8000

WORKDIR /app

COPY pyproject.toml README.md alembic.ini ./
COPY app ./app
COPY migrations ./migrations
COPY scripts ./scripts

RUN pip install --no-cache-dir . \
    && addgroup --system xiaoyi \
    && adduser --system --ingroup xiaoyi xiaoyi \
    && mkdir -p /app/data \
    && chown -R xiaoyi:xiaoyi /app/data

USER xiaoyi

EXPOSE 8000
VOLUME ["/app/data"]

HEALTHCHECK --interval=30s --timeout=5s --start-period=10s --retries=3 \
  CMD python -c "import os, urllib.request; urllib.request.urlopen('http://127.0.0.1:' + os.getenv('PORT', '8000') + '/health', timeout=3)"

# 启动顺序：先迁移数据库，再启动应用；应用侧 DB_AUTO_UPGRADE=false 只校验版本
CMD ["sh", "-c", "python -m app.cli deploy && DB_AUTO_UPGRADE=false python -m uvicorn app.main:app --host 0.0.0.0 --port ${PORT:-8000}"]
