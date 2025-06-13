FROM python:3.11-slim
ENV PYTHONUNBUFFERED=1

WORKDIR /usr/src/app
COPY requirements.txt .
COPY setup_playwright.sh .
RUN --mount=type=cache,target=/root/.cache \
    pip install -r requirements.txt
RUN bash setup_playwright.sh

COPY . /usr/src/app