FROM python:3.13-slim

ARG BUILD_COMMIT=unknown
LABEL org.opencontainers.image.revision="${BUILD_COMMIT}"

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_DISABLE_PIP_VERSION_CHECK=1 \
    PIP_NO_CACHE_DIR=1

WORKDIR /app
RUN addgroup --system django && adduser --system --ingroup django django
COPY requirements.txt ./
RUN apt-get update \
    && apt-get install --no-install-recommends -y git \
    && python -m pip install --upgrade pip \
    && python -m pip install -r requirements.txt \
    && apt-get purge -y git \
    && apt-get autoremove -y \
    && rm -rf /var/lib/apt/lists/*
COPY --chown=django:django . .
RUN sed -i 's/\r$//' /app/docker/entrypoint.sh \
    && cp /app/docker/entrypoint.sh /usr/local/bin/global-exchange-entrypoint \
    && chmod +x /usr/local/bin/global-exchange-entrypoint \
    && mkdir -p /app/staticfiles \
    && chown django:django /app/staticfiles
USER django
EXPOSE 8000
ENTRYPOINT ["/usr/local/bin/global-exchange-entrypoint"]
CMD ["python", "manage.py", "runserver", "0.0.0.0:8000"]
