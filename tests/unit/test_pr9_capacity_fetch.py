"""Fixed asset identity, bounded downloads and failure cleanup."""

import io
import json

import pytest

from tests.unit.test_pr9_capacity_transport import package as _transport_package
from tools import pr9_capacity_fetch as fetching

package = _transport_package


class Response(io.BytesIO):
    def __init__(self, data, url="https://release-assets.githubusercontent.com/fixture"):
        super().__init__(data)
        self.url = url

    def geturl(self):
        return self.url


def inputs(package, *, change=None, content=None, final_url=None):
    _, bundle, output = package
    metadata = json.loads((bundle / "transport.json").read_text())
    metadata["asset"] = {"status": "FIXED_ASSET", "id": 7}
    (bundle / "transport.json").write_text(json.dumps(metadata))
    asset = {
        "id": 7,
        "name": fetching.ASSET_NAME,
        "size": metadata["cipher_bytes"],
        "state": "uploaded",
        "browser_download_url": (
            f"https://github.com/{fetching.REPOSITORY}/releases/download/"
            f"{fetching.RELEASE_TAG}/{fetching.ASSET_NAME}"
        ),
    }
    asset.update(change or {})
    payload = (bundle / "ciphertext.aesgcm").read_bytes() if content is None else content
    calls = []

    def opener(request, timeout):
        assert timeout == 30 and request.get_header("Authorization") is None
        calls.append(request.full_url)
        if len(calls) == 1:
            assert request.full_url.endswith("/releases/assets/7")
            return Response(json.dumps(asset).encode())
        assert len(calls) == 2 and request.full_url == asset["browser_download_url"]
        return Response(
            payload, final_url or "https://release-assets.githubusercontent.com/fixture"
        )

    return bundle, output, opener, calls


def download(bundle, output, opener):
    return fetching.fetch(
        bundle / "source-manifest.json", bundle / "transport.json", output, opener=opener
    )


def test_fixed_asset_verified_without_any_credential(package):
    bundle, output, opener, calls = inputs(package)
    receipt = download(bundle, output, opener)
    assert receipt["asset_id"] == 7 and len(calls) == 2
    assert (output / "ciphertext.aesgcm").read_bytes() == (
        bundle / "ciphertext.aesgcm"
    ).read_bytes()
    assert output.stat().st_mode & 0o777 == 0o700
    assert (output / "ciphertext.aesgcm").stat().st_mode & 0o777 == 0o600


@pytest.mark.parametrize(
    "change",
    [
        {"id": True},
        {"id": 8},
        {"size": True},
        {"size": 1},
        {"state": "new"},
        {"name": "other"},
        {"browser_download_url": "https://example.test/arbitrary"},
    ],
)
def test_asset_metadata_cannot_redirect_or_relabel_input(package, change):
    bundle, output, opener, calls = inputs(package, change=change)
    with pytest.raises(ValueError, match="identity differs"):
        download(bundle, output, opener)
    assert len(calls) == 1 and not output.exists()


@pytest.mark.parametrize("corruption", ["short", "long", "same_length_changed", "http"])
def test_incomplete_or_unverified_download_never_remains(package, corruption):
    _, source, _ = package
    original = (source / "ciphertext.aesgcm").read_bytes()
    data = {
        "short": original[:-1],
        "long": original + b"x",
        "same_length_changed": bytes([original[0] ^ 1]) + original[1:],
        "http": original,
    }[corruption]
    bundle, output, opener, _ = inputs(
        package,
        content=data,
        final_url="http://example.test/cipher" if corruption == "http" else None,
    )
    with pytest.raises(ValueError):
        download(bundle, output, opener)
    assert not output.exists()


def test_asset_missing_is_hard_failure(package):
    bundle, output, _, _ = inputs(package)

    def unavailable(*args, **kwargs):
        raise OSError("synthetic unavailable asset")

    with pytest.raises(OSError):
        download(bundle, output, unavailable)
    assert not output.exists()


def test_existing_or_symlink_destination_is_never_deleted(package, tmp_path):
    bundle, output, opener, _ = inputs(package)
    output.symlink_to(tmp_path, target_is_directory=True)
    with pytest.raises(ValueError):
        download(bundle, output, opener)
    assert output.is_symlink() and tmp_path.exists()
