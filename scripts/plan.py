"""Plan a nightly run: the commit under test, the KiCad builds, the job matrix.

Run by the workflow's plan job. Reads TARGET_REPOSITORY and TARGET_REF (empty
on a scheduled run, which tests Bouni main), and GITHUB_TOKEN for the GitHub
API. Writes repository, sha, versions, matrix and key to $GITHUB_OUTPUT, or
prints them when run by hand.
"""

from collections.abc import Mapping
import json
import os
import re
import subprocess
import sys
import urllib.request

DEFAULT_REPOSITORY = "Bouni/kicad-jlcpcb-tools"
DEFAULT_REF = "main"
KICAD_RELEASES = "https://api.github.com/repos/KiCad/kicad-source-mirror/releases"
# The last releases of their series; they never move.
FIXED_VERSIONS = ("7.0.11", "8.0.9")
# Series whose newest patch release is tested.
LATEST_SERIES = ("9.0", "10.0")
RUNNERS = (("windows-latest", "Windows"), ("macos-latest", "macOS"))
FULL_SHA = re.compile(r"[0-9a-fA-F]{40}")
REPOSITORY_NAME = re.compile(r"[A-Za-z0-9_.-]+/[A-Za-z0-9_.-]+")


class PlanError(Exception):
    """The run cannot be planned; the message says why."""


def installer_names(version: str) -> tuple[str, str]:
    """Name the Windows and macOS installers a KiCad release must carry."""
    return f"kicad-{version}-x86_64.exe", f"kicad-unified-universal-{version}.dmg"


def has_installers(release: dict) -> bool:
    """Tell whether a release is published with both installers uploaded."""
    if release.get("draft") or release.get("prerelease"):
        return False
    names = {asset.get("name") for asset in release.get("assets", [])}
    return all(name in names for name in installer_names(release["tag_name"]))


def pick_versions(releases: list[dict]) -> list[str]:
    """Choose the KiCad builds to test, oldest first.

    The fixed releases must be complete. For each later series the newest
    complete patch release wins, compared by number, so 9.0.10 beats 9.0.9.
    """
    complete = {r["tag_name"] for r in releases if has_installers(r)}
    versions = []
    for version in FIXED_VERSIONS:
        if version not in complete:
            raise PlanError(
                f"KiCad {version} has no published Windows and macOS installers"
            )
        versions.append(version)
    for series in LATEST_SERIES:
        pattern = re.compile(re.escape(series) + r"\.(\d+)")
        patches = [
            int(match.group(1)) for tag in complete if (match := pattern.fullmatch(tag))
        ]
        if not patches:
            raise PlanError(f"no KiCad {series}.x release has both installers")
        versions.append(f"{series}.{max(patches)}")
    return versions


def resolve_sha(ls_remote: str, ref: str) -> str:
    """Find the commit a ref names in `git ls-remote` output.

    A full SHA is taken as is. A branch wins over a tag of the same name, and
    an annotated tag resolves to its commit (the peeled `^{}` line).
    """
    if FULL_SHA.fullmatch(ref):
        return ref.lower()
    refs = {}
    for line in ls_remote.splitlines():
        sha, _, name = line.partition("\t")
        if sha and name:
            refs[name.strip()] = sha.strip()
    for name in (f"refs/heads/{ref}", f"refs/tags/{ref}^{{}}", f"refs/tags/{ref}"):
        if name in refs:
            return refs[name]
    raise PlanError(
        f"no branch or tag named {ref!r}; give a branch, a tag or a full 40-character SHA"
    )


def build_matrix(versions: list[str]) -> dict:
    """List one lane per runner per KiCad build."""
    return {
        "include": [
            {
                "os": os_name,
                "label": label,
                "kicad": version,
                "major": version.split(".")[0],
            }
            for os_name, label in RUNNERS
            for version in versions
        ]
    }


def cache_key(sha: str, versions: list[str]) -> str:
    """Name a commit and KiCad set, so a scheduled run can skip a tested one."""
    return "tested-" + "-".join([sha, *versions])


def target(environ: Mapping[str, str]) -> tuple[str, str]:
    """Read the repository and ref to test; a scheduled run has neither."""
    repository = environ.get("TARGET_REPOSITORY", "").strip() or DEFAULT_REPOSITORY
    ref = environ.get("TARGET_REF", "").strip() or DEFAULT_REF
    if not REPOSITORY_NAME.fullmatch(repository):
        raise PlanError(f"repository must look like owner/name, not {repository!r}")
    return repository, ref


def fetch_releases(token: str) -> list[dict]:
    """Read every KiCad release from the GitHub API."""
    releases: list[dict] = []
    for page in range(1, 11):
        request = urllib.request.Request(
            f"{KICAD_RELEASES}?per_page=100&page={page}",
            headers={"Accept": "application/vnd.github+json"},
        )
        if token:
            request.add_header("Authorization", f"Bearer {token}")
        with urllib.request.urlopen(request, timeout=30) as response:
            batch = json.load(response)
        releases.extend(batch)
        if len(batch) < 100:
            break
    return releases


def remote_patterns(ref: str) -> list[str]:
    """Name the refs `git ls-remote` should list for a branch or tag.

    git lists an annotated tag's peeled commit (`^{}`) only when asked for it
    by name; without it a tag would resolve to the tag object.
    """
    return [f"refs/heads/{ref}", f"refs/tags/{ref}", f"refs/tags/{ref}^{{}}"]


def ls_remote(repository: str, ref: str) -> str:
    """List the remote refs that could match the requested ref."""
    result = subprocess.run(
        [
            "git",
            "ls-remote",
            f"https://github.com/{repository}.git",
            *remote_patterns(ref),
        ],
        capture_output=True,
        text=True,
        timeout=60,
        check=False,
    )
    if result.returncode != 0:
        raise PlanError(f"git ls-remote {repository} failed: {result.stderr.strip()}")
    return result.stdout


def main() -> int:
    """Plan the run and hand the results to the workflow."""
    try:
        repository, ref = target(os.environ)
        sha = resolve_sha(
            "" if FULL_SHA.fullmatch(ref) else ls_remote(repository, ref), ref
        )
        versions = pick_versions(fetch_releases(os.environ.get("GITHUB_TOKEN", "")))
    except PlanError as error:
        print(f"::error::{error}")
        return 1
    outputs = {
        "repository": repository,
        "sha": sha,
        "versions": json.dumps(versions),
        "matrix": json.dumps(build_matrix(versions), separators=(",", ":")),
        "key": cache_key(sha, versions),
    }
    destination = os.environ.get("GITHUB_OUTPUT")
    if destination:
        with open(destination, "a", encoding="utf-8") as handle:
            for name, value in outputs.items():
                handle.write(f"{name}={value}\n")
    else:
        for name, value in outputs.items():
            print(f"{name}={value}")
    summary = os.environ.get("GITHUB_STEP_SUMMARY")
    if summary:
        with open(summary, "a", encoding="utf-8") as handle:
            handle.write(
                f"Testing `{repository}` at `{ref}` (`{sha[:12]}`) "
                f"on KiCad {', '.join(versions)}\n"
            )
    return 0


if __name__ == "__main__":
    sys.exit(main())
