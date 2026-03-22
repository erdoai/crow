FROM python:3.13-slim

WORKDIR /app

COPY pyproject.toml .
COPY crow/ crow/

RUN pip install --no-cache-dir .

EXPOSE 8100

CMD ["crow", "serve"]
