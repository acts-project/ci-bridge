FROM python:3.10-slim

RUN adduser ci_relay
USER ci_relay

COPY pyproject.toml .
COPY poetry.lock .
COPY src src

RUN pip install . uvicorn[standard]

COPY CHECKS .


