FROM python:3.12-slim-bookworm

RUN apt-get update \
    && apt-get install --no-install-recommends -y iproute2 iputils-ping \
    && python -m pip install --no-cache-dir httpx psutil \
    && useradd --create-home --uid 10001 --shell /usr/sbin/nologin toolbox \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /workspace
USER toolbox
