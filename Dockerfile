FROM python:3.10-slim

COPY pyproject.toml .
COPY poetry.lock .
COPY src src

RUN pip install . uvicorn[standard]


