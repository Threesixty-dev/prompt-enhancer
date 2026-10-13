"""Exercise the packaged Bench API with an empty, ephemeral synthetic database."""

import json
import os
import subprocess
import time
import urllib.request
import uuid


def run(*args):
    return subprocess.check_output(args, text=True, stderr=subprocess.DEVNULL).strip()


def main():
    image, revision = os.environ["BENCH_CANDIDATE_IMAGE"], os.environ["DEPLOY_REVISION"]
    name = "bench-ci-" + uuid.uuid4().hex
    client = urllib.request.build_opener(urllib.request.ProxyHandler({}))
    try:
        run("docker", "run", "-d", "--name", name, "--read-only", "--cap-drop", "ALL",
            "--security-opt", "no-new-privileges:true", "--tmpfs", "/tmp:rw,noexec,nosuid,size=32m",
            "--tmpfs", "/data:rw,noexec,nosuid,size=16m,uid=10002,gid=10002",
            "-e", "BENCH_ORIGIN=http://bench.example.com",
            "-e", "BENCH_IMAGE_REPOSITORIES=registry.example.com/example/enhancer",
            "-p", "127.0.0.1::8088", image, "serve", "--host", "0.0.0.0", "--port", "8088")
        address = run("docker", "port", name, "8088/tcp")

        def get(path):
            request = urllib.request.Request("http://" + address + path, headers={"Host": "bench.example.com"})
            with client.open(request, timeout=3) as response:
                return response.read()

        for _ in range(30):
            try:
                health = json.loads(get("/health/ready"))
                if health == {"ready": True, "schemaVersion": "bench.v1", "revision": revision}:
                    break
            except OSError:
                pass
            time.sleep(1)
        else:
            raise RuntimeError("packaged_readiness_failed")
        assert json.loads(get("/api/runs")) == {"runs": [], "nextCursor": None}
        assert b'page-content' in get("/experiments")
        assert b'All runs' in get("/assets/app.js")
        assert b'operator-token' not in get("/experiments")
        print("Packaged Bench revision, empty API and routed client passed.")
    finally:
        subprocess.run(["docker", "rm", "-f", name], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)


if __name__ == "__main__":
    main()
