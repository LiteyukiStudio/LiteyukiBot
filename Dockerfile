FROM python:3.12-alpine

WORKDIR /liteyukibot

COPY main.py .
COPY pyproject.toml .
COPY liteyukibot/ .
COPY uv.lock .

RUN pip install uv

ENV UV_COMPILE_BYTECODE=1

RUN uv venv --python 3.12 && uv sync

CMD [".venv/bin/python3", "main.py"]