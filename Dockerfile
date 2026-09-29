FROM node:22-bookworm-slim AS frontend
WORKDIR /app
COPY package.json package-lock.json ./
RUN npm ci
COPY index.html tsconfig*.json vite.config.ts capacitor.config.ts ./
COPY src ./src
COPY public ./public
RUN npm run build

FROM python:3.12-slim
WORKDIR /app
RUN apt-get update && apt-get install -y --no-install-recommends ffmpeg fonts-dejavu-core && rm -rf /var/lib/apt/lists/*
COPY server/requirements.txt ./server/requirements.txt
RUN pip install --no-cache-dir -r server/requirements.txt
RUN mkdir -p /opt/piper && python -m piper.download_voices --data-dir /opt/piper pt_BR-faber-medium
COPY server ./server
COPY alembic.ini ./alembic.ini
COPY --from=frontend /app/dist ./dist
ENV FRONTEND_DIST_DIR=/app/dist
ENV PIPER_MODEL_PATH=/opt/piper/pt_BR-faber-medium.onnx
ENV GROWTH_WORKER_ENABLED=1
EXPOSE 8000
CMD ["sh", "-c", "alembic upgrade head && uvicorn server.api:create_app --factory --host 0.0.0.0 --port ${PORT:-8000} --no-access-log"]
