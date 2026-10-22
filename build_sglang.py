#!/usr/bin/env python3
"""Build the sglang wheel from the sglang-miles branch.

Follows upstream's PR-wheel recipe (.github/workflows/release-pypi-pr.yml in
sgl-project/sglang): pin a static version, build against the torch the
pyproject's build requirements name, then let upstream's
scripts/release/prepare_sglang_wheel.py repair the wheel to a manylinux tag and
smoke-test its Rust extension. Upstream builds on a plain GitHub-hosted Ubuntu
runner with its preinstalled Rust toolchain, and so does this.

The version is the last release tag on the branch with a +miles.g<commit> local
label (e.g. 0.5.22+miles.g3a938213c1), so every sglang-miles commit gets its own
version and Miles can pin the exact one it was tested with.
"""

import json
import os
import re
import shutil
import subprocess
import sys
import tomllib

SGLANG_REPO = "https://github.com/sgl-project/sglang.git"
SGLANG_REF_DEFAULT = "sglang-miles"
# Records the commit the wheel was built from; upload syncs it next to the wheel.
SOURCE_MANIFEST = "sglang-source.json"


def _git(args, cwd):
    return subprocess.check_output(["git", *args], cwd=cwd, text=True).strip()


def _wheel_version(repo_dir, commit):
    # Same tag resolution upstream's setuptools-scm hook uses (get_version_tag.py).
    tag = subprocess.check_output(
        [sys.executable, "scripts/release/get_version_tag.py", "--tag-only"], cwd=repo_dir, text=True
    ).strip()
    if not re.fullmatch(r"v\d+\.\d+\.\d+(\.post\d+|rc\d+)?", tag):
        raise RuntimeError(f"unexpected sglang release tag {tag!r}")
    return f"{tag[1:]}+miles.g{commit[:10]}"


def _pin_version(pyproject_path, version):
    with open(pyproject_path) as f:
        text = f.read()
    if 'dynamic = ["version"]' not in text or '\nname = "sglang"\n' not in text:
        raise RuntimeError(f"{pyproject_path} no longer declares a dynamic sglang version; update the pin")
    text = text.replace('dynamic = ["version"]', "dynamic = []")
    text = text.replace('\nname = "sglang"\n', f'\nname = "sglang"\nversion = "{version}"\n')
    with open(pyproject_path, "w") as f:
        f.write(text)


def _build_requirements(pyproject_path):
    with open(pyproject_path, "rb") as f:
        return tomllib.load(f)["build-system"]["requires"]


def build(ref, out_dir, run):
    """Build the sglang wheel at *ref* into *out_dir*, with its source manifest."""
    repo_dir = "/tmp/sglang"
    if os.path.exists(repo_dir):
        shutil.rmtree(repo_dir)
    manifest = os.path.join(out_dir, SOURCE_MANIFEST)
    if os.path.exists(manifest):
        os.remove(manifest)

    # Blobless with tags: the version needs the release tags reachable from ref.
    run(["git", "clone", "--filter=blob:none", "--no-checkout", SGLANG_REPO, repo_dir])
    run(["git", "fetch", "--tags", "origin", ref], cwd=repo_dir)
    run(["git", "checkout", "-f", "FETCH_HEAD"], cwd=repo_dir)
    commit = _git(["rev-parse", "HEAD"], repo_dir)
    version = _wheel_version(repo_dir, commit)
    print(f"sglang {ref} @ {commit} -> {version}")

    python_dir = os.path.join(repo_dir, "python")
    pyproject = os.path.join(python_dir, "pyproject.toml")
    _pin_version(pyproject, version)
    for name in ("README.md", "LICENSE"):
        shutil.copy2(os.path.join(repo_dir, name), python_dir)

    run([sys.executable, "-m", "pip", "install", "auditwheel", "build", "patchelf", *_build_requirements(pyproject)])
    run([sys.executable, "-m", "build", "--wheel", "--no-isolation"], cwd=python_dir)
    run([sys.executable, "scripts/release/prepare_sglang_wheel.py", "python/dist"], cwd=repo_dir)

    (wheel,) = [f for f in os.listdir(os.path.join(python_dir, "dist")) if f.endswith(".whl")]
    if f"-{version}-" not in wheel:
        raise RuntimeError(f"built {wheel}, expected version {version}")
    os.makedirs(out_dir, exist_ok=True)
    shutil.copy2(os.path.join(python_dir, "dist", wheel), out_dir)
    with open(manifest, "w") as f:
        json.dump({"repo": SGLANG_REPO, "ref": ref, "commit": commit, "version": version}, f, indent=2)
        f.write("\n")
    shutil.rmtree(repo_dir)
