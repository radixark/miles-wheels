#!/usr/bin/env python3
"""Build the sglang wheel from sglang-miles with upstream's own wheel recipe (release-pypi.yml).

Versioned <tag sglang-miles is built on>.post<commits since it>+miles.g<commit>: builds sort by
commit, and a Miles wheel can pin the exact one it was tested with. The build host's glibc sets the
manylinux tag.
"""

import json
import os
import platform
import shutil
import subprocess
import sys

from packaging.version import Version

import build_sglang_gateway

SGLANG_REPO = "https://github.com/sgl-project/sglang.git"
SGLANG_REF_DEFAULT = "sglang-miles"
SOURCE_MANIFEST = "sglang-source.json"


def _git(args, cwd):
    return subprocess.check_output(["git", *args], cwd=cwd, text=True).strip()


def _wheel_version(repo_dir, commit):
    # HEAD's own tag: upstream's get_version_tag.py takes the highest tag on any branch
    tag = _git(["describe", "--tags", "--abbrev=0", "--match", "v[0-9]*", "HEAD"], repo_dir)
    count = _git(["rev-list", "--count", f"{tag}..HEAD"], repo_dir)
    return str(Version(f"{tag[1:]}.post{count}+miles.g{commit[:10]}"))


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
    import tomllib  # 3.11+, needed only by this step

    with open(pyproject_path, "rb") as f:
        return tomllib.load(f)["build-system"]["requires"]


def build(ref, arch, out_dir, run, bootstrap_rust=True):
    """Build the sglang wheel at *ref* into *out_dir*, with its source manifest."""
    # the upload picks its release from --arch, not from the wheel's platform tag
    machine = {"x86": "x86_64"}.get(arch, arch)
    if platform.machine() != machine:
        raise RuntimeError(f"--arch {arch} on a {platform.machine()} host would mislabel the sglang wheel")
    repo_dir = "/tmp/sglang"
    if os.path.exists(repo_dir):
        shutil.rmtree(repo_dir)
    manifest = os.path.join(out_dir, SOURCE_MANIFEST)
    if os.path.exists(manifest):
        os.remove(manifest)

    # the version needs the release tags
    run(["git", "clone", "--filter=blob:none", "--no-checkout", SGLANG_REPO, repo_dir])
    run(["git", "fetch", "--tags", "origin", ref], cwd=repo_dir)
    run(["git", "checkout", "-f", "FETCH_HEAD"], cwd=repo_dir)
    commit = _git(["rev-parse", "HEAD"], repo_dir)
    version = _wheel_version(repo_dir, commit)
    print(f"sglang {ref} @ {commit} -> {version}")

    # protoc for the bundled gRPC extension; the script writes /usr/local
    sudo = [] if os.geteuid() == 0 else ["sudo"]
    run([*sudo, "bash", "scripts/ci/utils/install_protoc.sh"], cwd=repo_dir)
    build_sglang_gateway._ensure_rust_and_maturin(bootstrap_rust)

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
