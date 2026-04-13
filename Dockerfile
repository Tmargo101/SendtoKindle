FROM python:3.12-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1

WORKDIR /app

COPY pyproject.toml README.md ./
COPY send_to_kindle ./send_to_kindle

RUN pip install --no-cache-dir .

COPY .env.example ./
COPY config/users.example.yaml ./config/users.example.yaml

ENTRYPOINT ["python", "-m", "send_to_kindle.main"]
CMD ["api"]
