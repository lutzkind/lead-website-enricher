import json
import os
import re
import urllib.parse
import urllib.error
import urllib.request


DEFAULT_SERVICE_URL_VAR = "u/admin/lead_website_enricher_service_url_v2"
DEFAULT_COOLIFY_BASE_URL_VAR = "u/admin/coolify_base_url"
DEFAULT_COOLIFY_ACCESS_TOKEN_VAR = "u/admin/coolify_access_token"
DEFAULT_APP_UUID_VAR = "u/admin/lead_website_enricher_app_uuid"
DEFAULT_COOLIFY_BASE_URL = "https://coolify.luxeillum.com"
DEFAULT_APP_UUID = "kfzqxy5rbq69kiilwq41hbz5"
CONTAINER_NAME_RE = re.compile(r"Container\\s+([a-z0-9-]+)\\s+(?:Created|Starting|Started)")


def main(
    rows: list[dict],
    source: str | None = None,
    provider: str = "openserp",
    engines: list[str] = ["ecosia", "bing"],
    per_query_limit: int = 5,
):
    """
    summary: Enrich a batch of lead rows with candidate websites.
    description: Calls the deployed lead-website-enricher service with raw lead rows, returning structured website-candidate results and audit statistics.
    """
    service_url = _load_secret(DEFAULT_SERVICE_URL_VAR, "LEAD_WEBSITE_ENRICHER_URL").rstrip("/")
    if not service_url:
        service_url = _resolve_service_url()
    payload = {
        "rows": rows,
        "provider": provider,
        "engines": engines,
        "per_query_limit": per_query_limit,
    }
    if source:
        payload["source"] = source

    req = urllib.request.Request(
        f"{service_url}/enrich",
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


def _resolve_service_url() -> str:
    coolify_base_url = _load_secret(
        DEFAULT_COOLIFY_BASE_URL_VAR,
        "COOLIFY_BASE_URL",
        DEFAULT_COOLIFY_BASE_URL,
    ).rstrip("/")
    coolify_access_token = _load_secret(
        DEFAULT_COOLIFY_ACCESS_TOKEN_VAR,
        "COOLIFY_ACCESS_TOKEN",
    )
    app_uuid = _load_secret(
        DEFAULT_APP_UUID_VAR,
        "LEAD_WEBSITE_ENRICHER_APP_UUID",
        DEFAULT_APP_UUID,
    ).strip()

    if not coolify_access_token:
        raise RuntimeError(
            "COOLIFY_ACCESS_TOKEN is required when LEAD_WEBSITE_ENRICHER_URL is not set."
        )

    app = _request_json(
        "GET",
        f"{coolify_base_url}/api/v1/applications/{app_uuid}",
        coolify_access_token,
    )
    if app.get("status") != "running:healthy":
        raise RuntimeError(
            f"Lead website enricher app is not healthy in Coolify: {app.get('status')}"
        )

    deployment_list = _request_json(
        "GET",
        f"{coolify_base_url}/api/v1/deployments/applications/{app_uuid}",
        coolify_access_token,
    )
    if isinstance(deployment_list, dict):
        deployment_list = [deployment_list]
    deployment = deployment_list[0] if deployment_list else None
    if not deployment:
        raise RuntimeError("Could not find any Coolify deployments for lead-website-enricher.")

    container_name = _extract_latest_container_name(deployment.get("logs", ""))
    if not container_name:
        raise RuntimeError("Could not extract the current lead-website-enricher container name from Coolify logs.")

    port = str(app.get("ports_exposes") or "8000").split(",")[0].strip()
    return f"http://{container_name}:{port}"


def _extract_latest_container_name(logs_blob: str) -> str | None:
    names = CONTAINER_NAME_RE.findall(logs_blob or "")
    return names[-1] if names else None


def _request_json(method: str, url: str, bearer_token: str):
    req = urllib.request.Request(
        url,
        headers={
            "Authorization": f"Bearer {bearer_token}",
            "Accept": "application/json",
        },
        method=method,
    )
    with urllib.request.urlopen(req, timeout=60) as response:
        return json.loads(response.read().decode("utf-8"))


def _load_secret(variable_path: str, env_name: str, default: str = "") -> str:
    env_value = os.environ.get(env_name)
    if env_value:
        return env_value.strip()
    try:
        import wmill  # type: ignore

        value = wmill.get_variable(variable_path)
        if value is not None:
            return str(value).strip()
    except Exception:
        pass
    base_internal_url = os.environ.get("BASE_INTERNAL_URL", "").rstrip("/")
    workspace = os.environ.get("WM_WORKSPACE", "").strip()
    wm_token = os.environ.get("WM_TOKEN", "").strip()
    if base_internal_url and workspace and wm_token:
        quoted = urllib.parse.quote(variable_path, safe="")
        req = urllib.request.Request(
            f"{base_internal_url}/api/w/{workspace}/variables/get_value/{quoted}",
            headers={"Authorization": f"Bearer {wm_token}"},
            method="GET",
        )
        try:
            with urllib.request.urlopen(req, timeout=30) as response:
                value = response.read().decode("utf-8")
            if value:
                return str(json.loads(value) if value.strip().startswith('"') else value).strip()
        except Exception:
            pass
    return default
