# Onboarding wizard image (FastAPI + Jinja templates).
FROM python:3.11

ENV PYTHONUNBUFFERED=1 PIP_NO_CACHE_DIR=1
WORKDIR /app

COPY pyproject.toml README.md ./
COPY src ./src
RUN pip install --upgrade pip && pip install .

EXPOSE 8088
CMD ["python", "-m", "aia.onboarding.main"]
