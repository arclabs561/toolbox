ARG BASE_IMAGE=python:3.12-slim
FROM ${BASE_IMAGE}

RUN apt-get update \
    && apt-get install --no-install-recommends -y iproute2 iputils-ping \
    && pip install --no-cache-dir httpx psutil \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /workspace
COPY ips/ips /workspace/ips/ips
COPY tests/docker/smoke.sh /workspace/smoke.sh
RUN chmod +x /workspace/smoke.sh

CMD ["/workspace/smoke.sh"]
