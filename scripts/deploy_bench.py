"""Deploy only the Bench API Compose application through the Coolify API.

No runtime configuration or log bodies are printed. Controller and Bench Access
credentials remain separate, redirects/proxies are disabled, and health must
report the source revision baked into the image before deployment is confirmed.
"""

from __future__ import annotations

import argparse
import json
import os
import re
import sys
import time
import urllib.error
import urllib.request

from deploy_coolify import HTTP_CLIENT_HEADERS, NoRedirect, access_headers, checked_url, controller_json


def revision(env):
    value = env.get("DEPLOY_REVISION", "")
    if re.fullmatch(r"[a-f0-9]{40}", value) is None:
        raise ValueError("revision_invalid")
    if env.get("DEPLOY_BRANCH") != "main":
        raise ValueError("main_required")
    return value


def controller(env):
    revision(env)
    origin = checked_url(env.get("BENCH_COOLIFY_URL", ""), webhook=False)
    ids = [env.get(key, "") for key in ("BENCH_COOLIFY_SERVICE_UUID", "BENCH_COOLIFY_API_UUID")]
    if any(re.fullmatch(r"[A-Za-z0-9_-]{1,64}", value) is None for value in ids):
        raise ValueError("bench_target_required")
    token = env.get("COOLIFY_TOKEN", "")
    if not 16 <= len(token) <= 1024 or not token.isascii() or any(ord(c) <= 32 or ord(c) >= 127 for c in token):
        raise ValueError("controller_token_invalid")
    headers = {**HTTP_CLIENT_HEADERS, "Authorization": "Bearer " + token,
               **access_headers(env, "COOLIFY", required=True)}
    return origin + "/api/v1/services/" + ids[0] + "/applications/" + ids[1], headers


def image_ref(env):
    return "local/enhancement-bench:api-" + revision(env)


def opener():
    return urllib.request.build_opener(urllib.request.ProxyHandler({}), NoRedirect())


def inspect_target(env, client):
    url, headers = controller(env)
    current = controller_json(client, url, headers)
    if current.get("uuid") != env["BENCH_COOLIFY_API_UUID"] or current.get("name") != "bench-api":
        raise RuntimeError("bench_api_target_mismatch")
    return url, headers, current


def deploy(env, client):
    image = image_ref(env)
    url, headers, _ = inspect_target(env, client)
    service_url = url.rsplit("/applications/", 1)[0]
    variable = controller_json(client, service_url + "/envs", headers, method="PATCH", body={
        "key": "BENCH_SOURCE_REVISION", "value": revision(env), "is_literal": True,
    })
    # Ordinary tokens return metadata only; prove the baked revision after build.
    if (variable.get("key") != "BENCH_SOURCE_REVISION"
        or ("value" in variable and variable["value"] != revision(env))):
        raise RuntimeError("source_revision_unconfirmed")
    controller_json(client, url, headers, method="PATCH", body={"image": image})
    _, _, updated = inspect_target(env, client)
    if updated.get("image") != image:
        raise RuntimeError("image_pin_unconfirmed")
    # Coolify v4.3.23 starts this service with compose up --no-deps --build. Host layers stay cached.
    controller_json(client, url + "/start?force=true", headers, method="POST")
    print("Bench API source pinned; build queued on Coolify. Health verification follows.")


def health_settings(env):
    revision(env)
    origin = checked_url(env.get("BENCH_PUBLIC_URL", ""), webhook=False)
    headers = {**HTTP_CLIENT_HEADERS, "Cache-Control": "no-cache",
               **access_headers(env, "BENCH_CF", required=True)}
    return origin + "/health/ready", headers


def ready(env, client, *, exact):
    url, headers = health_settings(env)
    request = urllib.request.Request(url, headers=headers)
    with client.open(request, timeout=10) as response:
        payload = response.read(4097)
        if response.status != 200 or len(payload) > 4096:
            return False
        body = json.loads(payload)
    return (isinstance(body, dict) and body.get("ready") is True
            and body.get("schemaVersion") == "bench.v1"
            and (not exact or body.get("revision") == revision(env)))


def verify(env, client, *, monotonic=time.monotonic, sleep=time.sleep):
    health_settings(env)
    deadline, consecutive = monotonic() + 300, 0
    while monotonic() < deadline:
        try:
            consecutive = consecutive + 1 if ready(env, client, exact=True) else 0
            if consecutive >= 2:
                print("The expected Bench source revision passed two health checks.")
                return
        except (OSError, ValueError, urllib.error.URLError):
            consecutive = 0
        sleep(5)
    raise RuntimeError("bench_revision_health_timeout")


def main(argv=None):
    parser = argparse.ArgumentParser()
    parser.add_argument("mode", choices=["check-controller", "check-health", "deploy", "verify"])
    mode = parser.parse_args(argv).mode
    try:
        client = opener()
        if mode == "check-controller":
            inspect_target(os.environ, client)
            print("The configured target is the Bench API container.")
        elif mode == "check-health":
            if not ready(os.environ, client, exact=False):
                raise RuntimeError("bench_health_access_unconfirmed")
            print("Bench readiness is accessible with its gateway credentials.")
        elif mode == "deploy":
            deploy(os.environ, client)
        else:
            verify(os.environ, client)
    except urllib.error.HTTPError as error:
        # Status is useful for policy diagnosis; URLs, headers and bodies are not.
        print(f"Bench deployment step failed: {mode} (HTTP {error.code}).", file=sys.stderr)
        return 1
    except (OSError, ValueError, RuntimeError, urllib.error.URLError) as error:
        known = {"revision_invalid", "main_required", "deployment_url_invalid",
                 "bench_target_required", "controller_token_invalid",
                 "cloudflare_access_credentials_incomplete", "cloudflare_access_credentials_invalid",
                 "cloudflare_access_credentials_required", "source_revision_unconfirmed", "bench_api_target_mismatch", "image_pin_unconfirmed",
                 "bench_health_access_unconfirmed", "bench_revision_health_timeout"}
        reason = str(error) if type(error) in {ValueError, RuntimeError} and str(error) in known else "request_unconfirmed"
        print(f"Bench deployment step failed: {mode} ({reason}).", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
