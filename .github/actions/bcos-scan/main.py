#!/usr/bin/env python3
# SPDX-License-Identifier: MIT
"""GitHub Action wrapper for RustChain's canonical BCOS v2 engine."""

from __future__ import annotations

import json
import os
import subprocess
import sys
import tempfile
import urllib.error
import urllib.request
from pathlib import Path
from typing import Any


ENGINE_REVISION = "2e3318f646cbd30a6120979bfed1c062563fa22c"
ENGINE_URL = (
    "https://raw.githubusercontent.com/Scottcjn/Rustchain/"
    f"{ENGINE_REVISION}/tools/bcos_engine.py"
)
COMMENT_MARKER = "<!-- bcos-v2-action -->"


def request_json(
    url: str,
    *,
    method: str = "GET",
    token: str = "",
    payload: dict[str, Any] | None = None,
) -> Any:
    data = None
    headers = {"Accept": "application/vnd.github+json", "User-Agent": "bcos-action-v1"}
    if token:
        headers["Authorization"] = f"Bearer {token}"
        headers["X-GitHub-Api-Version"] = "2022-11-28"
    if payload is not None:
        data = json.dumps(payload).encode("utf-8")
        headers["Content-Type"] = "application/json"
    request = urllib.request.Request(url, data=data, headers=headers, method=method)
    with urllib.request.urlopen(request, timeout=30) as response:
        body = response.read()
    return json.loads(body) if body else {}


def load_event(path: str) -> dict[str, Any]:
    if not path:
        return {}
    try:
        return json.loads(Path(path).read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as error:
        raise RuntimeError(f"cannot read GitHub event payload: {error}") from error


def download_engine(destination: Path) -> None:
    request = urllib.request.Request(ENGINE_URL, headers={"User-Agent": "bcos-action-v1"})
    try:
        with urllib.request.urlopen(request, timeout=30) as response:
            source = response.read()
    except urllib.error.URLError as error:
        raise RuntimeError(f"cannot download the BCOS engine: {error}") from error
    if b"class BCOSEngine" not in source or b"bcos-attestation/v2" not in source:
        raise RuntimeError("downloaded BCOS engine failed its source sanity check")
    destination.write_bytes(source)


def run_engine(engine: Path, workspace: str, tier: str, reviewer: str) -> dict[str, Any]:
    command = [sys.executable, str(engine), workspace, "--tier", tier, "--json"]
    if reviewer:
        command.extend(["--reviewer", reviewer])
    result = subprocess.run(command, text=True, capture_output=True, check=False)
    if result.returncode not in (0, 1):
        raise RuntimeError(f"BCOS engine failed ({result.returncode}): {result.stderr.strip()}")
    try:
        report = json.loads(result.stdout)
    except json.JSONDecodeError as error:
        raise RuntimeError(f"BCOS engine returned invalid JSON: {error}") from error
    required = ("trust_score", "cert_id", "tier_met", "score_breakdown")
    missing = [name for name in required if name not in report]
    if missing:
        raise RuntimeError(f"BCOS engine report is missing: {', '.join(missing)}")
    return report


def report_comment(report: dict[str, Any]) -> str:
    score = int(report["trust_score"])
    color = "brightgreen" if score >= 80 else "yellow" if score >= 60 else "red"
    badge = f"https://img.shields.io/badge/BCOS-{score}%2F100-{color}"
    rows = [
        f"| {name.replace('_', ' ').title()} | {points} |"
        for name, points in report["score_breakdown"].items()
    ]
    met = "yes" if report["tier_met"] else "no"
    return "\n".join(
        [
            COMMENT_MARKER,
            "## BCOS v2 scan",
            "",
            f"![BCOS trust score]({badge})",
            "",
            f"- Certificate: `{report['cert_id']}`",
            f"- Requested tier: `{report['tier']}`",
            f"- Tier met: **{met}**",
            "",
            "| Check | Points |",
            "|---|---:|",
            *rows,
            "",
            f"[Verify this certificate](https://rustchain.org/bcos/verify/{report['cert_id']})",
        ]
    )


def post_pr_comment(report: dict[str, Any], event: dict[str, Any], token: str) -> None:
    pull_request = event.get("pull_request")
    repository = event.get("repository", {}).get("full_name") or os.environ.get("GITHUB_REPOSITORY")
    if not pull_request or not repository:
        return
    if not token:
        raise RuntimeError("github-token is required to post the BCOS pull-request comment")
    number = pull_request["number"]
    base_url = f"https://api.github.com/repos/{repository}/issues/{number}/comments"
    comments = request_json(f"{base_url}?per_page=100", token=token)
    existing = next((item for item in comments if COMMENT_MARKER in item.get("body", "")), None)
    payload = {"body": report_comment(report)}
    if existing:
        request_json(existing["url"], method="PATCH", token=token, payload=payload)
    else:
        request_json(base_url, method="POST", token=token, payload=payload)


def anchor_if_merged(report: dict[str, Any], event: dict[str, Any], node_url: str) -> None:
    pull_request = event.get("pull_request", {})
    if not report["tier_met"] or not (
        event.get("action") == "closed" and pull_request.get("merged") is True
    ):
        return
    if not node_url.startswith(("https://", "http://")):
        raise RuntimeError("node-url must be an http(s) URL")
    payload = dict(report)
    payload["repo"] = event.get("repository", {}).get("full_name", "")
    payload["pr_number"] = pull_request.get("number")
    payload["merged_commit"] = pull_request.get("merge_commit_sha")
    request_json(f"{node_url.rstrip('/')}/attest", method="POST", payload=payload)


def write_outputs(report: dict[str, Any], output_path: str) -> None:
    values = {
        "trust_score": report["trust_score"],
        "cert_id": report["cert_id"],
        "tier_met": str(bool(report["tier_met"])).lower(),
    }
    if output_path:
        with Path(output_path).open("a", encoding="utf-8") as output:
            for name, value in values.items():
                output.write(f"{name}={value}\n")
    for name, value in values.items():
        print(f"{name}={value}")


def main() -> int:
    tier = os.environ.get("INPUT_TIER", "L1").upper()
    if tier not in {"L0", "L1", "L2"}:
        raise RuntimeError("tier must be one of L0, L1, or L2")
    reviewer = os.environ.get("INPUT_REVIEWER", "")
    workspace = os.environ.get("GITHUB_WORKSPACE", os.getcwd())
    event = load_event(os.environ.get("GITHUB_EVENT_PATH", ""))
    with tempfile.TemporaryDirectory(prefix="bcos-action-") as temp_dir:
        engine = Path(temp_dir) / "bcos_engine.py"
        download_engine(engine)
        report = run_engine(engine, workspace, tier, reviewer)
    write_outputs(report, os.environ.get("GITHUB_OUTPUT", ""))
    post_pr_comment(report, event, os.environ.get("INPUT_GITHUB_TOKEN", ""))
    anchor_if_merged(report, event, os.environ.get("INPUT_NODE_URL", "https://rustchain.org"))
    return 0 if report["tier_met"] else 1


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except (RuntimeError, urllib.error.URLError, urllib.error.HTTPError) as error:
        print(f"::error::{error}", file=sys.stderr)
        raise SystemExit(2)
