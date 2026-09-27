# BCOS v2 GitHub Action

This directory contains the auditable source for `Scottcjn/bcos-action@v1`.
The action downloads the official
[`tools/bcos_engine.py`](https://github.com/Scottcjn/Rustchain/blob/main/tools/bcos_engine.py)
at a pinned RustChain revision, runs it against the caller's checkout, publishes
its `trust_score`, `cert_id`, and `tier_met` fields, and posts the engine's score
breakdown on pull requests. A successful scan of a confirmed merged pull request
is submitted to the configured RustChain node.

## Usage

```yaml
name: BCOS

on:
  pull_request:
    types: [opened, synchronize, reopened, closed]

permissions:
  contents: read
  pull-requests: write

jobs:
  scan:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4
      - id: bcos
        uses: Scottcjn/bcos-action@v1
        with:
          tier: L1
          reviewer: ${{ github.event.pull_request.requested_reviewers[0].login }}
          node-url: https://rustchain.org
      - run: |
          echo "score=${{ steps.bcos.outputs.trust_score }}"
          echo "certificate=${{ steps.bcos.outputs.cert_id }}"
          echo "tier met=${{ steps.bcos.outputs.tier_met }}"
```

Do not run this action with `pull_request_target` against an untrusted checkout.
The example uses the least privileges needed to read the repository and maintain
one BCOS result comment.

## Inputs

| Input | Default | Description |
|---|---|---|
| `tier` | `L1` | Requested certification tier: `L0`, `L1`, or `L2` |
| `reviewer` | empty | Human reviewer handle; required by the engine for L2 |
| `node-url` | `https://rustchain.org` | RustChain node used for merge anchoring |
| `github-token` | `github.token` | Token used to create or update the PR comment |

## Outputs

| Output | Description |
|---|---|
| `trust_score` | Official engine trust score from 0 to 100 |
| `cert_id` | Content-derived BCOS certificate ID |
| `tier_met` | `true` when the requested tier threshold is met |

The action preserves the engine's exit semantics: a tier miss returns exit code
1 after writing the outputs and PR comment. Download, report, comment, and anchor
errors return exit code 2 so they cannot be mistaken for a successful attestation.

## Publishing

The contents of this directory are ready to be published at the root of the
`Scottcjn/bcos-action` repository and tagged `v1`. Keeping the implementation in
this repository makes the proposed release reviewable before it receives that
stable action tag.

## License

MIT. See [LICENSE](LICENSE).
