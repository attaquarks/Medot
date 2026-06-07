# Shared image for the Python services (gateway, business-agent, health-agent).
# The compose file overrides CMD per service.
FROM python:3.11

ENV PYTHONUNBUFFERED=1 PIP_NO_CACHE_DIR=1
WORKDIR /app

COPY pyproject.toml README.md ./
COPY src ./src
RUN pip install --upgrade pip && pip install .

# Default command (overridden by docker-compose per service).
CMD ["python", "-m", "aia.gateway.main"]
