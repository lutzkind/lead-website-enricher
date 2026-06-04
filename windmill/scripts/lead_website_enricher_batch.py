import json
import os
import urllib.error
import urllib.request


SERVICE_URL = os.environ.get(
    "LEAD_WEBSITE_ENRICHER_URL",
    "http://lead-website-enricher:8000",
).rstrip("/")


def main(
    rows: list[dict],
    source: str | None = None,
    provider: str = "openserp",
    engines: list[str] = ["duck", "ecosia", "bing"],
    per_query_limit: int = 5,
):
    """
    summary: Enrich a batch of lead rows with candidate websites.
    description: Calls the deployed lead-website-enricher service with raw lead rows, returning structured website-candidate results and audit statistics.
    """
    payload = {
        "rows": rows,
        "provider": provider,
        "engines": engines,
        "per_query_limit": per_query_limit,
    }
    if source:
        payload["source"] = source

    req = urllib.request.Request(
        f"{SERVICE_URL}/enrich",
        data=json.dumps(payload).encode("utf-8"),
        headers={"Content-Type": "application/json", "Accept": "application/json"},
        method="POST",
    )
    try:
        with urllib.request.urlopen(req, timeout=300) as resp:
            return json.loads(resp.read().decode("utf-8"))
    except urllib.error.HTTPError as exc:
        body = exc.read().decode("utf-8", errors="replace")
        raise RuntimeError(f"lead-website-enricher returned HTTP {exc.code}: {body}")
