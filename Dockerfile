FROM python:3.11-slim
ENV PYTHONUNBUFFERED=1

WORKDIR /usr/src/app
COPY requirements.txt .
RUN --mount=type=cache,target=/root/.cache \
    pip install -r requirements.txt

COPY . /usr/src/app