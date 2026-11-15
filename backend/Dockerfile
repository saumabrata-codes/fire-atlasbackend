FROM python:3.12-slim
WORKDIR /app/backend
COPY pyproject.toml ./
RUN pip install --no-cache-dir .
COPY app ./app
COPY source_backend ./source_backend
COPY migrations ./migrations
COPY alembic.ini ./
CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000"]
