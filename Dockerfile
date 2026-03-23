FROM node:22-slim AS frontend

WORKDIR /web
COPY web/package.json web/package-lock.json ./
RUN npm ci
COPY web/ .
RUN npm run build

FROM python:3.13-slim

WORKDIR /app

COPY pyproject.toml .
COPY crow/ crow/

RUN pip install --no-cache-dir .

# Copy built SPA
COPY --from=frontend /web/dist web/dist/

EXPOSE 8100

CMD ["crow", "serve"]
