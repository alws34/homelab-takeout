# Verifying a release

Every `v*` tag produces a GitHub Release built by
[`.github/workflows/build-release.yml`](../.github/workflows/build-release.yml),
a reusable workflow that GitHub runs in isolation from the calling workflow. Each
release has four assets:

| Asset | What it is |
|---|---|
| `homelab-takeout-X.Y.Z.tar.gz` | Source tarball (`git archive` of the tagged commit) |
| `homelab-takeout-X.Y.Z.tar.gz.sigstore.json` | Keyless Sigstore signature bundle (cosign) |
| `homelab-takeout-X.Y.Z.tar.gz.intoto.jsonl` | SLSA build provenance attestation (also stored on GitHub) |
| `homelab-takeout-X.Y.Z.spdx.json` | SBOM of the source tree (SPDX JSON) |

There is no prebuilt container image. You build it yourself from the verified source.

## 1. Download

```bash
VERSION=1.2.3   # the release you want, without the leading "v"
gh release download "v$VERSION" -R alws34/homelab-takeout
```

## 2. Verify the build provenance (GitHub CLI)

```bash
gh attestation verify "homelab-takeout-$VERSION.tar.gz" \
  -R alws34/homelab-takeout \
  --signer-workflow alws34/homelab-takeout/.github/workflows/build-release.yml \
  --source-ref "refs/tags/v$VERSION"
```

This checks that the tarball's sha256 matches an attestation signed by
`build-release.yml` in this repository, for that tag. In a terminal it ends with
`✓ Verification succeeded!`; in a script or pipe it prints nothing on success, so
check the exit status (0) instead. To check against the
downloaded attestation instead of fetching it from GitHub, add
`--bundle "homelab-takeout-$VERSION.tar.gz.intoto.jsonl"`.

## 3. Verify the Sigstore signature (cosign)

```bash
cosign verify-blob \
  --bundle "homelab-takeout-$VERSION.tar.gz.sigstore.json" \
  --certificate-identity-regexp '^https://github.com/alws34/homelab-takeout/.github/workflows/build-release.yml@refs/tags/v' \
  --certificate-oidc-issuer https://token.actions.githubusercontent.com \
  "homelab-takeout-$VERSION.tar.gz"
```

It prints `Verified OK`. Needs cosign 2.4 or newer (the bundle is in the Sigstore
bundle v0.3 format). Without cosign installed, run the same command from the
official image, with the downloaded files in the current folder:

```bash
docker run --rm -u "$(id -u)" -v "$PWD:/w:ro" -w /w gcr.io/projectsigstore/cosign:v3.0.6 \
  verify-blob --bundle "homelab-takeout-$VERSION.tar.gz.sigstore.json" \
  --certificate-identity "https://github.com/alws34/homelab-takeout/.github/workflows/build-release.yml@refs/tags/v$VERSION" \
  --certificate-oidc-issuer https://token.actions.githubusercontent.com \
  "homelab-takeout-$VERSION.tar.gz"
```

To pin the exact tag instead of any `v*` tag, use
`--certificate-identity "https://github.com/alws34/homelab-takeout/.github/workflows/build-release.yml@refs/tags/v$VERSION"`
(as in the container example).

Both commands must succeed (exit status 0). If either fails, do not use the
tarball.

The SBOM (`homelab-takeout-$VERSION.spdx.json`) lists every Python and npm package
of the release with its version, for checking against advisories.

## 4. Build from the verified tarball

```bash
tar -xzf "homelab-takeout-$VERSION.tar.gz"
cd "homelab-takeout-$VERSION"
cp .env.example .env && chmod 600 .env
mkdir -p backups logs state && chmod 700 backups logs state
docker compose up -d --build
```

The container uses host networking and listens on port 9100, so stop any other
instance first (`docker compose down` in its folder).

To upgrade an existing install, extract the new tarball next to the old one and
move your `.env`, `config/`, `backups/`, `logs/` and `state/` across (or copy the
new files over the old checkout), then run `docker compose up -d --build`.

## Optional: reproduce the tarball

The tarball is a plain `git archive` of the tag, so you can rebuild it and
compare checksums (gzip output can differ between git versions; the extracted
files will always match):

```bash
git clone https://github.com/alws34/homelab-takeout.git && cd homelab-takeout
git archive --format=tar.gz --prefix="homelab-takeout-$VERSION/" "v$VERSION" | sha256sum
```
