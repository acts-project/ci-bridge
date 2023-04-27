FROM python:3.10-slim

ENV USER=ci_relay
RUN adduser --gecos "" --disabled-password $USER

RUN pip install --no-cache-dir poetry uvicorn

RUN mkdir /app
WORKDIR /app

COPY pyproject.toml /app
COPY poetry.lock /app

ENV PATH=/home/$USER/.local/bin:$PATH

RUN poetry export -o requirements.txt

RUN pip install --no-cache-dir -r requirements.txt

COPY src src
COPY CHECKS .
COPY Procfile .

RUN pip install .

USER $USER
CMD uvicorn ci_relay.web:create_app --factory --port 5000 --host 0.0.0.0
