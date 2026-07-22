ARG BASE_IMAGE=python:3.12-slim
FROM ${BASE_IMAGE}

ARG INSTALL_DEPS=1
RUN if [ "$INSTALL_DEPS" = "1" ]; then \
        apt-get update \
        && apt-get install --no-install-recommends -y iproute2 iputils-ping \
        && pip install --no-cache-dir httpx psutil \
        && rm -rf /var/lib/apt/lists/*; \
    fi

WORKDIR /workspace
COPY ips/ips /workspace/ips/ips
COPY ips/metrics.py /workspace/ips/metrics.py
COPY ips/net_platform.py /workspace/ips/net_platform.py
COPY ips/neighbors.py /workspace/ips/neighbors.py
COPY tests/docker/smoke.sh /workspace/smoke.sh

CMD ["/bin/sh", "/workspace/smoke.sh"]
