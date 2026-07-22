ARG BASE_IMAGE=toolbox-pinglet-base:python3.12
FROM ${BASE_IMAGE}

WORKDIR /workspace
COPY pinglet/pinglet /workspace/pinglet/pinglet
COPY pinglet/metrics.py /workspace/pinglet/metrics.py
COPY pinglet/net_platform.py /workspace/pinglet/net_platform.py
COPY pinglet/neighbors.py /workspace/pinglet/neighbors.py
COPY tests/docker/smoke.sh /workspace/smoke.sh

CMD ["/bin/sh", "/workspace/smoke.sh"]
