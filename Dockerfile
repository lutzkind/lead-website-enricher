FROM python:3.12-slim

ENV PYTHONDONTWRITEBYTECODE=1
ENV PYTHONUNBUFFERED=1
ENV PORT=3000
ENV PYTHONPATH=/app/src
ENV OPENSERP_BASE_URL=http://openserp-managed:7000
ENV LEAD_WEBSITE_ENRICHER_ENGINES=ecosia,bing,duckduckgo
ENV LEAD_WEBSITE_ENRICHER_OPENSERP_TIMEOUT_SECONDS=8
ENV LEAD_WEBSITE_ENRICHER_PER_LEAD_TIMEOUT_SECONDS=18
ENV LEAD_WEBSITE_ENRICHER_PER_QUERY_LIMIT=3

WORKDIR /app

RUN apt-get update \
    && apt-get install -y --no-install-recommends curl \
    && rm -rf /var/lib/apt/lists/*

COPY pyproject.toml README.md /app/
COPY src /app/src

EXPOSE 3000

CMD ["python3", "-m", "lead_website_enricher.api"]
