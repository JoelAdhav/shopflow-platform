# ---- Stage 1: builder. Installs dependencies into a virtualenv. ----
FROM python:3.13.18-slim-trixie AS builder
WORKDIR /build
RUN python -m venv /opt/venv
ENV PATH=/opt/venv/bin:$PATH
# Copy only requirements first: this layer is cached until requirements change.
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt
# Runtime copy of the venv without pip: 13MB smaller, and an attacker inside
# the container cannot "pip install" tools.
RUN cp -a /opt/venv /opt/venv-runtime && \
    rm -rf /opt/venv-runtime/lib/python3.13/site-packages/pip* /opt/venv-runtime/bin/pip*

# ---- Stage 2: test. Adds dev tools. Never shipped. ----
# Build with: docker build --target test -t shopflow-api-test .
FROM builder AS test
COPY requirements-dev.txt .
RUN pip install --no-cache-dir -r requirements-dev.txt
WORKDIR /srv
COPY pyproject.toml .
COPY app ./app
COPY tests ./tests
CMD ["sh", "-c", "ruff check . && pytest -v"]

# ---- Stage 3: runtime. Only the venv and the app code. ----
FROM python:3.13.18-slim-trixie AS runtime
ENV PATH=/opt/venv/bin:$PATH \
    PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1
# Fixed numeric UID: Kubernetes "runAsNonRoot" can verify a number, not a name.
RUN useradd --uid 10001 --no-create-home --shell /usr/sbin/nologin app
COPY --from=builder /opt/venv-runtime /opt/venv
WORKDIR /srv
COPY app ./app
USER 10001
EXPOSE 8000
CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000"]
