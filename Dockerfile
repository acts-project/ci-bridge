FROM python:3.10-slim

ENV USER=ci_relay
RUN adduser $USER
USER $USER

COPY pyproject.toml .
COPY poetry.lock .
COPY src src

RUN pip install . uvicorn[standard]

COPY CHECKS .
ENV PATH=/home/$USER/.local/bin:$PATH

