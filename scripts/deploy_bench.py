"""Deploy only the Bench API Compose application through the Coolify API.

No runtime configuration or log bodies are read or printed. Controller metadata
verifies the selected container; the protected Bench readiness endpoint verifies
the serving revision with separate gateway credentials. Redirects and proxies
are disabled.
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
from uuid import uuid4

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
    started_ms = time.time_ns() // 1_000_000
    controller_json(client, url + "/start?force=true", headers, method="POST")
    print("Bench API source pinned; build queued on Coolify. Health verification follows.")
    return started_ms


def controller_ready(env, client):
    _, _, current = inspect_target(env, client)
    return current.get("image") == image_ref(env) and current.get("status") == "running:healthy"


def bench_connection(env):
    revision(env)
    origin = checked_url(env.get("BENCH_DELIVERY_URL", ""), webhook=False)
    return origin, {**HTTP_CLIENT_HEADERS, **access_headers(env, "BENCH_CF", required=True),
                    "Cache-Control": "no-cache"}


def bench_ready(env, client):
    origin, headers = bench_connection(env)
    # A unique request plus no-store responses avoids accepting cached readiness.
    request = urllib.request.Request(origin + "/health/ready?check=" + uuid4().hex, headers=headers)
    with client.open(request, timeout=30) as response:
        if (response.status != 200
                or response.headers.get("Content-Type", "").split(";", 1)[0] != "application/json"
                or "no-store" not in {p.strip() for p in response.headers.get("Cache-Control", "").lower().split(",")}
                or response.headers.get("Age", "0") != "0"):
            return False
        payload = response.read(4097)
    if len(payload) > 4096:
        return False
    try:
        result = json.loads(payload)
    except ValueError:
        return False
    return (isinstance(result, dict) and result.get("ready") is True
            and result.get("schemaVersion") == "bench.v1" and result.get("revision") == revision(env))


def verify(env, client, *, public=False, monotonic=time.monotonic, sleep=time.sleep):
    bench_connection(env) if public else controller(env)
    check = bench_ready if public else controller_ready
    deadline, consecutive = monotonic() + 300, 0
    while monotonic() < deadline:
        try:
            consecutive = consecutive + 1 if check(env, client) else 0
            if consecutive >= 2:
                print("The expected Bench source revision passed two protected readiness checks." if public
                      else "The expected Bench image passed two controller health checks.")
                return
        except urllib.error.HTTPError as error:
            if error.code in {301, 302, 303, 307, 308, 401, 403, 404}:
                raise
            consecutive = 0
        except (OSError, ValueError, urllib.error.URLError):
            consecutive = 0
        sleep(5)
    raise RuntimeError("bench_revision_health_timeout")


def main(argv=None):
    parser = argparse.ArgumentParser()
    parser.add_argument("mode", choices=["check-controller", "deploy", "verify", "verify-bench"])
    mode = parser.parse_args(argv).mode
    try:
        client = opener()
        if mode == "check-controller":
            inspect_target(os.environ, client)
            print("The configured target is the Bench API container.")
        elif mode == "deploy":
            deploy(os.environ, client)
            verify(os.environ, client)
        else:
            verify(os.environ, client, public=mode == "verify-bench")
    except urllib.error.HTTPError as error:
        # Status is useful for policy diagnosis; URLs, headers and bodies are not.
        print(f"Bench deployment step failed: {mode} (HTTP {error.code}).", file=sys.stderr)
        return 1
    except (OSError, ValueError, RuntimeError, urllib.error.URLError) as error:
        known = {"revision_invalid", "main_required", "deployment_url_invalid",
                 "bench_target_required", "controller_token_invalid",
                 "cloudflare_access_credentials_incomplete", "cloudflare_access_credentials_invalid",
                 "cloudflare_access_credentials_required", "source_revision_unconfirmed", "bench_api_target_mismatch", "image_pin_unconfirmed",
                 "bench_revision_health_timeout"}
        reason = str(error) if type(error) in {ValueError, RuntimeError} and str(error) in known else "request_unconfirmed"
        print(f"Bench deployment step failed: {mode} ({reason}).", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
