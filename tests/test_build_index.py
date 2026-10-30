"""build_index.py lists every published wheel once, with its hash, and nothing else."""

import re
from pathlib import Path

import pytest

import build_index

WHEEL = "sglang-0.5.22.post62+miles.g6136e6d2bd-cp312-cp312-manylinux_2_34_x86_64.whl"


def _asset(name, digest="sha256:" + "a" * 64, state="uploaded"):
    return {
        "name": name,
        "state": state,
        "digest": digest,
        "browser_download_url": f"https://github.com/radixark/miles-wheels/releases/download/t/{name}",
    }


RELEASES = {
    "repos/radixark/miles-wheels/releases?per_page=100": [
        {"id": 1, "tag_name": "sglang-miles-2026w44-x86_64", "draft": False},
        {"id": 2, "tag_name": "sglang-miles-2026w45-x86_64", "draft": True},
        {"id": 3, "tag_name": "cu130-torch214-x86_64", "draft": False},
    ],
    "repos/radixark/miles-wheels/releases/1/assets?per_page=100": [
        _asset(WHEEL),
        _asset("sglang-source.json"),
        _asset("sglang-0.5.22.post63+miles.g0000000000-cp312-cp312-manylinux_2_34_x86_64.whl", state="starter"),
    ],
    "repos/radixark/miles-wheels/releases/2/assets?per_page=100": [_asset("sglang-9-cp312-cp312-linux_x86_64.whl")],
    "repos/radixark/miles/releases?per_page=100": [
        {"id": 9, "tag_name": "v0.1.4", "draft": False},
        {"id": 8, "tag_name": "tpu-stack-before-rebase", "draft": False},
    ],
    "repos/radixark/miles/releases/9/assets?per_page=100": [
        _asset("miles-0.1.4-py3-none-any.whl", digest=None),
        _asset("miles-0.1.4.tar.gz"),
    ],
}


@pytest.fixture
def api(monkeypatch):
    calls = []

    def fake(path):
        calls.append(path)
        return RELEASES[path]

    monkeypatch.setattr(build_index, "_api", fake)
    return calls


def test_only_uploaded_wheels_of_non_draft_releases_under_the_prefix_are_indexed(tmp_path, api):
    listed = build_index.build(["radixark/miles-wheels:sglang-miles-", "radixark/miles:v"], str(tmp_path))
    assert listed == {"miles": ["miles-0.1.4-py3-none-any.whl"], "sglang": [WHEEL]}
    assert "repos/radixark/miles-wheels/releases/3/assets?per_page=100" not in api  # not under the prefix
    assert "repos/radixark/miles/releases/8/assets?per_page=100" not in api


def test_links_carry_the_sha256_when_github_recorded_one(tmp_path, api):
    build_index.build(["radixark/miles-wheels:sglang-miles-", "radixark/miles:v"], str(tmp_path))
    sglang = Path(tmp_path, "sglang/index.html").read_text()
    assert re.search(rf'href="https://github.com/.*/{re.escape(WHEEL)}#sha256={"a" * 64}"', sglang)
    miles = Path(tmp_path, "miles/index.html").read_text()
    assert "#sha256" not in miles and "miles-0.1.4-py3-none-any.whl" in miles
    assert '<a href="miles/">miles</a>' in Path(tmp_path, "index.html").read_text()


def test_the_same_filename_in_two_releases_is_an_error(tmp_path, monkeypatch):
    releases = dict(RELEASES)
    releases["repos/radixark/miles-wheels/releases/2/assets?per_page=100"] = [_asset(WHEEL)]
    releases["repos/radixark/miles-wheels/releases?per_page=100"] = [
        {"id": 1, "tag_name": "sglang-miles-2026w44-x86_64", "draft": False},
        {"id": 2, "tag_name": "sglang-miles-2026w45-x86_64", "draft": False},
    ]
    monkeypatch.setattr(build_index, "_api", lambda path: releases[path])
    with pytest.raises(AssertionError, match="more than one release"):
        build_index.build(["radixark/miles-wheels:sglang-miles-"], str(tmp_path))
