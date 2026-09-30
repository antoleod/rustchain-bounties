# BCOS Scan - Reusable GitHub Action (BCOS v2)

A reusable GitHub Action that runs the BCOS v2 engine against any repository,
publishes `trust_score`, `cert_id`, and `tier_met` outputs, posts a PR comment
with a score badge and breakdown, and anchors the attestation to RustChain when
the scan runs for a merged PR.

## Usage

```yaml
name: BCOS

on:
  pull_request:
    types: [opened, synchronize, reopened, closed]

jobs:
  bcos-scan:
    runs-on: ubuntu-latest
    permissions:
      contents: read
      pull-requests: write
      issues: write

    steps:
      - uses: actions/checkout@v4
        with:
          fetch-depth: 0

      - name: BCOS Scan
        uses: Scottcjn/bcos-action@v1
        with:
          tier: L1
          reviewer: octocat
          node-url: https://rustchain.org
          pr-number: ${{ github.event.pull_request.number }}
          repo-token: ${{ secrets.GITHUB_TOKEN }}
```

## Inputs

| Input | Required | Description |
|-------|----------|-------------|
| `tier` | No | Review tier: `L0`, `L1`, or `L2`. Default: `L1` |
| `reviewer` | No | GitHub login of the assigned reviewer. Required for an L2 pass. |
| `node-url` | No | RustChain node URL. Default: `https://rustchain.org` |
| `pr-number` | No | PR number to comment on. Auto-detected from the event payload. |
| `repo-token` | No | Token for PR comments. Defaults to `github.token` when available. |
| `engine-url` | No | Raw URL for `tools/bcos_engine.py`. Defaults to Scottcjn/Rustchain `main`. |

## Outputs

| Output | Description |
|--------|-------------|
| `trust_score` | BCOS trust score (0-100) |
| `cert_id` | BCOS attestation certificate ID, for example `BCOS-a1b2c3d4` |
| `tier_met` | Whether the required tier threshold was met (`true` or `false`) |

## Engine

The action downloads and runs
[`tools/bcos_engine.py`](https://github.com/Scottcjn/Rustchain/blob/main/tools/bcos_engine.py)
from the Rustchain repo. The engine emits the BCOS v2 attestation JSON and
calculates the score breakdown defined in the
[BCOS spec](https://github.com/Scottcjn/Rustchain/blob/main/docs/BEACON_CERTIFIED_OPEN_SOURCE.md).

## Attestation Schema

```json
{
  "schema": "bcos-attestation/v2",
  "cert_id": "BCOS-a1b2c3d4",
  "tier": "L1",
  "trust_score": 75,
  "tier_met": true,
  "reviewer": "hubot",
  "commit_sha": "abc123def456...",
  "score_breakdown": {
    "license_compliance": 20,
    "vulnerability_scan": 25,
    "static_analysis": 10
  },
  "commitment": "..."
}
```

## PR Comment

The action posts or updates a formatted PR comment with:

- Trust score
- Cert ID
- Tier and tier pass/fail status
- Score breakdown from the engine
- Direct link to the BCOS verification page
- Embedded BCOS badge image served from the node

## RustChain Anchoring

On `pull_request.closed` events where `pull_request.merged == true`, the action
POSTs the attestation JSON to `${node-url}/attest`. If the node is unavailable,
the JSON remains in `bcos-artifacts/bcos-attestation.json`.

## Example With Outputs

```yaml
- id: bcos
  uses: Scottcjn/bcos-action@v1
  with:
    tier: L0

- run: |
    echo "score=${{ steps.bcos.outputs.trust_score }}"
    echo "cert=${{ steps.bcos.outputs.cert_id }}"
    echo "met=${{ steps.bcos.outputs.tier_met }}"
```

## License

MIT. The action runs the MIT-licensed BCOS v2 engine from Rustchain.
