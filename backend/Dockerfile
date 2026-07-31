# DocMind 后端镜像（构建上下文 = 仓库根目录）
FROM python:3.11-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1

WORKDIR /app

COPY backend/requirements.txt .
RUN pip install --no-cache-dir uv
RUN uv pip install --system --no-cache -r requirements.txt

COPY backend/app ./app
COPY VERSION .

# 数据目录（docker-compose 挂载卷，可被环境变量覆盖）
ENV DOCMIND_DATA_DIR=/data
EXPOSE 8000

HEALTHCHECK --interval=10s --timeout=5s --retries=5 \
  CMD python -c "import urllib.request; urllib.request.urlopen('http://127.0.0.1:8000/api/health', timeout=4)"

CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000"]