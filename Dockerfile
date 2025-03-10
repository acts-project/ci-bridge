FROM python:3.13-slim as builder

ENV USER=ci_relay
RUN adduser --gecos "" --disabled-password $USER

COPY --from=ghcr.io/astral-sh/uv:0.6 /uv /bin/uv

RUN mkdir /app
WORKDIR /app

COPY pyproject.toml /app
COPY uv.lock /app
COPY src /app/src


RUN uv sync --frozen --no-editable --no-cache --no-dev --python /usr/local/bin/python3.13

FROM python:3.13-slim
COPY --from=builder /app /app

WORKDIR /app

ENV PATH=/home/$USER/.local/bin:$PATH
ENV PATH="/app/.venv/bin:$PATH"

USER $USER
CMD uvicorn ci_relay.web:create_app --factory --port 5000 --host 0.0.0.0
