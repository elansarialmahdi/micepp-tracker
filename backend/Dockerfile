FROM python:3.12-slim AS runtime

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_DISABLE_PIP_VERSION_CHECK=1

WORKDIR /app

RUN addgroup --system app && adduser --system --ingroup app app

COPY pyproject.toml ./
COPY app ./app
COPY alembic.ini ./
COPY alembic ./alembic
RUN pip install --no-cache-dir .

USER app
EXPOSE 8000

CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000"]

FROM runtime AS development
USER root
RUN pip install --no-cache-dir ".[dev]"
USER app

FROM runtime AS scanner
USER root
ARG WHATWEB_COMMIT=d279d93042d034f3fd29d5a893d44ccc0595d3f8
ARG WHATWEB_SHA256=f239c8d23b9b1d92d896351236ce0c00f08316897f8581212228adf13c521495
RUN apt-get update \
    && apt-get install -y --no-install-recommends ca-certificates curl nmap ruby ruby-addressable \
    && curl -fsSL "https://codeload.github.com/urbanadventurer/WhatWeb/tar.gz/${WHATWEB_COMMIT}" -o /tmp/whatweb.tar.gz \
    && echo "${WHATWEB_SHA256}  /tmp/whatweb.tar.gz" | sha256sum -c - \
    && mkdir -p /opt/whatweb \
    && tar -xzf /tmp/whatweb.tar.gz --strip-components=1 -C /opt/whatweb \
    && chmod 0755 /opt/whatweb/whatweb \
    && /opt/whatweb/whatweb --version \
    && rm -f /tmp/whatweb.tar.gz \
    && apt-get purge -y --auto-remove curl \
    && rm -rf /var/lib/apt/lists/*
USER app
