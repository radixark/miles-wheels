#!/usr/bin/env python3
"""Write a PEP 503 simple index over GitHub release assets, for ``pip``/``uv --extra-index-url``.

Every release whose tag starts with a given prefix is indexed; each link points at the release
download with its sha256, so nothing is hosted twice:

    python build_index.py --out site/simple \\
        --releases radixark/miles-wheels:sglang-miles- --releases radixark/miles:v
"""

import argparse
import html
import json
import os
import re
import urllib.request


def _api(path: str) -> list[dict]:
    """Every item of a paginated list endpoint. Both repos are public; GH_TOKEN only lifts the rate limit."""
    headers = {"Accept": "application/vnd.github+json"}
    if token := os.environ.get("GH_TOKEN"):
        headers["Authorization"] = f"Bearer {token}"
    url, items = f"https://api.github.com/{path}", []
    while url:
        with urllib.request.urlopen(urllib.request.Request(url, headers=headers)) as response:
            items += json.load(response)
            links = {rel: href for href, rel in re.findall(r'<([^>]+)>; rel="(\w+)"', response.headers.get("Link", ""))}
        url = links.get("next")
    return items


def _wheels(repo: str, tag_prefix: str) -> list[dict]:
    assets = []
    for release in _api(f"repos/{repo}/releases?per_page=100"):
        if release["tag_name"].startswith(tag_prefix) and not release["draft"]:
            assets += _api(f"repos/{repo}/releases/{release['id']}/assets?per_page=100")
    # wheels only: a .tar.gz may be a binary bundle (sgl-model-gateway), not an sdist
    return [a for a in assets if a["name"].endswith(".whl") and a["state"] == "uploaded"]


def _project(filename: str) -> str:
    """The PEP 503 normalized project name of a wheel."""
    return re.sub(r"[-_.]+", "-", filename.split("-")[0]).lower()


def _link(asset: dict) -> str:
    url = asset["browser_download_url"]
    digest = asset.get("digest")  # None on assets uploaded before GitHub recorded one
    return f"{url}#sha256={digest.removeprefix('sha256:')}" if digest else url


def _page(title: str, links: list[tuple[str, str]]) -> str:
    anchors = "\n".join(f'    <a href="{html.escape(href)}">{html.escape(text)}</a><br/>' for href, text in links)
    return f"<!DOCTYPE html>\n<html>\n  <body>\n    <h1>{html.escape(title)}</h1>\n{anchors}\n  </body>\n</html>\n"


def build(releases: list[str], out: str) -> dict[str, list[str]]:
    projects: dict[str, dict[str, str]] = {}
    for spec in releases:
        repo, tag_prefix = spec.split(":", 1)
        for asset in _wheels(repo, tag_prefix):
            files = projects.setdefault(_project(asset["name"]), {})
            # one filename in two releases would make the index ambiguous
            assert asset["name"] not in files, f"{asset['name']} is in more than one release"
            files[asset["name"]] = _link(asset)

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
    parser.add_argument("--out", required=True, help="directory to write, e.g. site/simple")
    parser.add_argument(
        "--releases", action="append", required=True, help="<owner/repo>:<tag prefix> to index (repeatable)"
    )
    args = parser.parse_args()
    for project, files in build(args.releases, args.out).items():
        print(f"{project}: {len(files)} file(s)")


if __name__ == "__main__":
    main()
