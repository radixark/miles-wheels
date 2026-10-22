#!/usr/bin/env python3
"""Write a PEP 503 simple index over miles-wheels release assets, for ``pip``/``uv --index-url``.

Each link points at the release download with its sha256, so nothing is hosted twice:

    python build_index.py --out site/cu130 --release sglang-miles-x86_64 --release sglang-miles-aarch64
"""

import argparse
import html
import json
import os
import re
import subprocess

REPO = "radixark/miles-wheels"


def _assets(release: str) -> list[dict]:
    out = subprocess.check_output(
        ["gh", "api", "--paginate", f"repos/{REPO}/releases/tags/{release}", "--jq", ".assets[]"], text=True
    )
    return [json.loads(line) for line in out.splitlines()]


def _project(filename: str) -> str | None:
    """The PEP 503 normalized project name of a wheel, or None for any other asset."""
    # wheels only: a .tar.gz may be a binary bundle (sgl-model-gateway), not an sdist
    if not filename.endswith(".whl"):
        return None
    return re.sub(r"[-_.]+", "-", filename.split("-")[0]).lower()


def _page(title: str, links: list[tuple[str, str]]) -> str:
    anchors = "\n".join(f'    <a href="{html.escape(href)}">{html.escape(text)}</a><br/>' for href, text in links)
    return f"<!DOCTYPE html>\n<html>\n  <body>\n    <h1>{html.escape(title)}</h1>\n{anchors}\n  </body>\n</html>\n"


def build(releases: list[str], out: str) -> dict[str, list[str]]:
    projects: dict[str, dict[str, str]] = {}
    for release in releases:
        for asset in _assets(release):
            project = _project(asset["name"])
            if project is None:
                continue
            files = projects.setdefault(project, {})
            # one filename in two releases would make the index ambiguous
            assert asset["name"] not in files, f"{asset['name']} is in more than one of {releases}"
            digest = asset["digest"].removeprefix("sha256:")
            files[asset["name"]] = f"{asset['browser_download_url']}#sha256={digest}"

    os.makedirs(out, exist_ok=True)
    with open(os.path.join(out, "index.html"), "w") as f:
        f.write(_page("Simple index", [(f"{project}/", project) for project in sorted(projects)]))
    for project, files in projects.items():
        os.makedirs(os.path.join(out, project), exist_ok=True)
        with open(os.path.join(out, project, "index.html"), "w") as f:
            f.write(_page(f"Links for {project}", [(files[name], name) for name in sorted(files)]))
    return {project: sorted(files) for project, files in sorted(projects.items())}


def main():
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--out", required=True, help="directory to write, e.g. site/cu130")
    parser.add_argument("--release", action="append", required=True, help="release tag to index (repeatable)")
    args = parser.parse_args()
    for project, files in build(args.release, args.out).items():
        print(f"{project}: {len(files)} file(s)")


if __name__ == "__main__":
    main()
