# Same three-stage layout as services/api/Dockerfile. Comments there explain each stage.
FROM python:3.13.18-slim-trixie AS builder
WORKDIR /build
RUN python -m venv /opt/venv
ENV PATH=/opt/venv/bin:$PATH
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt
# Runtime copy of the venv without pip: 13MB smaller, and an attacker inside
# the container cannot "pip install" tools.
RUN cp -a /opt/venv /opt/venv-runtime && \
    rm -rf /opt/venv-runtime/lib/python3.13/site-packages/pip* /opt/venv-runtime/bin/pip*

FROM builder AS test
COPY requirements-dev.txt .
RUN pip install --no-cache-dir -r requirements-dev.txt
WORKDIR /srv
COPY pyproject.toml .
COPY worker ./worker
COPY tests ./tests
CMD ["sh", "-c", "ruff check . && pytest -v"]

FROM python:3.13.18-slim-trixie AS runtime
ENV PATH=/opt/venv/bin:$PATH \
    PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1
# Security patching (found by Trivy, see docs/decisions/0004):
# 1. apt-get upgrade pulls OS fixes released after the base image was built.
# 2. The base image ships its own pip, which bundles old urllib3/msgpack/setuptools.
#    The app never runs pip, so remove it.
RUN apt-get update && \
    apt-get upgrade -y --no-install-recommends && \
    rm -rf /var/lib/apt/lists/* && \
    rm -rf /usr/local/lib/python3.13/site-packages/pip* /usr/local/bin/pip*
RUN useradd --uid 10001 --no-create-home --shell /usr/sbin/nologin app
COPY --from=builder /opt/venv-runtime /opt/venv
WORKDIR /srv
COPY worker ./worker
USER 10001
EXPOSE 9100
# Exec form (JSON array): python is PID 1 and receives SIGTERM directly.
CMD ["python", "-m", "worker.main"]
