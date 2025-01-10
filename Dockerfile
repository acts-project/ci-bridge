FROM python:3.10-slim

ENV USER=ci_relay
RUN adduser --gecos "" --disabled-password $USER

RUN pip install --no-cache-dir uv

RUN mkdir /app
WORKDIR /app

COPY . /app

ENV PATH=/home/$USER/.local/bin:$PATH

RUN uv sync --frozen --no-editable

USER $USER
CMD uv run --frozen --no-editable uvicorn ci_relay.web:create_app --factory --port 5000 --host 0.0.0.0
