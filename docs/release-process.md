# Release process

## Versioning

| Thing | Scheme | Current |
|-------|--------|---------|
| Repository | SemVer `MAJOR.MINOR.PATCH[-pre]` | `0.2.0-dev` |
| Product identity (os-release `VERSION_ID`) | `MAJOR.MINOR` per Ubuntu LTS base | `1.0` (on 26.04) |
| Build (os-release `BUILD_ID`) | repository version | `0.2.0-dev` |
| Debian packages (9 sources) | `<semver>` with `~` for pre-releases | `0.2.0~dev1` |
| nexus-cli, nexus-core, nexus-center, nexus-agent | SemVer, tracks the repository | `0.2.0` |

All NexusOS packages share one version and are released together. Development
changelog entries use the `UNRELEASED` distribution; release entries use `resolute`.

## Release checklist

1. **Freeze** — create `release/X.Y.Z` from `develop`; only fixes land there.
2. **Bump versions** — `dch -v X.Y.Z -D resolute` in each `packages/*/debian/changelog`,
   `nexus_cli/__init__.py`, `packages/nexus-cli/pyproject.toml`, `configs/os-release/*`
   (`BUILD_ID`/`NEXUSOS_BUILD`), `CHANGELOG.md`. `validate_debian.py` checks alignment.
3. **Validate** — `scripts/validation/run-all.sh` and
   `validate_manifests.py --check-archive` must pass.
4. **Build packages** — `scripts/package/build-in-container.sh`; lintian without errors;
   `test-packages-container.sh` passes.
5. **Build ISO** — production pipeline (once implemented) in CI from the release tag only.
6. **Validate ISO** — `inspect-iso.sh --deep`; VM checklist in `docs/installation.md`
   (UEFI, Secure Boot, BIOS, install to virtual disk, encrypted install, removal tests);
   ISO size budget ≤ 5 GB.
7. **Checksums and signatures** — `scripts/build/checksums.sh generate`; sign
   `SHA256SUMS` with the offline NexusOS release key (`gpg --detach-sign --armor`).
   Publish the key fingerprint in the README and over a second channel.
8. **GitHub release** — a maintainer tags `vX.Y.Z` (signed tag) on `main` after the
   release PR is reviewed and merged, creates a **draft** release, attaches the ISO,
   `.deb`s, `SHA256SUMS`, `SHA256SUMS.asc`, package manifest and SBOM, and publishes
   after a second maintainer verifies the checksums.

CI never publishes releases or uploads ISOs from feature branches; the workflows
in `.github/workflows` only upload short-lived review artefacts.

## APT repository (future)

NexusOS packages will be served from a signed APT repository (`reprepro` or
`aptly`) with a dedicated signing key, a `nexusos-archive-keyring` package and
a deb822 `.sources` file that uses `Signed-By:`.
