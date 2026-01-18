# docker/web.Dockerfile
# Web PROD: build Quasar SPA y servir con Nginx (proxy /api -> backend)
# Nota: el build-arg VITE_API_BASE_URL es opcional; si el frontend no lo usa, no afecta.

FROM node:20-bullseye-slim AS builder

WORKDIR /app

ARG VITE_API_BASE_URL=/api
ENV VITE_API_BASE_URL=${VITE_API_BASE_URL}

COPY frontend/ /app/frontend/
WORKDIR /app/frontend

RUN npm ci
RUN npm run build

# ---------------------

FROM nginx:1.27-alpine

COPY docker/nginx/default.conf /etc/nginx/conf.d/default.conf
COPY --from=builder /app/frontend/dist/spa/ /usr/share/nginx/html/

EXPOSE 80
