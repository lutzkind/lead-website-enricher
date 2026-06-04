FROM python:3.12-slim

ENV PYTHONDONTWRITEBYTECODE=1
ENV PYTHONUNBUFFERED=1
ENV PORT=8000
ENV PYTHONPATH=/app/src
ENV OPENSERP_BASE_URL=http://openserp:7000

WORKDIR /app

COPY pyproject.toml README.md /app/
COPY src /app/src

EXPOSE 8000

CMD ["python3", "-m", "lead_website_enricher.api"]
