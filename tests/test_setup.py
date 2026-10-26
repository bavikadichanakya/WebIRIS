"""Unit tests for Setup Manager and Verifier."""

from pathlib import Path
from iris.setup.manifest import COMPONENTS_MANIFEST
from iris.setup.verifier import Verifier


def test_manifest_definitions():
    assert "smollm3_3b_model" in COMPONENTS_MANIFEST
    assert "wake_word_model" in COMPONENTS_MANIFEST
    assert "stt_engine" in COMPONENTS_MANIFEST
    assert "tts_engine" in COMPONENTS_MANIFEST


def test_verifier_file_exists(tmp_path: Path):
    test_file = tmp_path / "sample.bin"
    assert not Verifier.verify_file_exists(str(test_file))

    test_file.write_bytes(b"hello world")
    assert Verifier.verify_file_exists(str(test_file), min_size_bytes=5)


def test_verifier_sha256(tmp_path: Path):
    test_file = tmp_path / "data.txt"
    test_file.write_text("IRIS")
    # SHA-256 for 'IRIS'
    expected_hash = "beccf0c91f56d418c84e5cb684eff4012e563863774a907f4e6c3f6e19f55fd3"
    assert Verifier.calculate_sha256(str(test_file)) == expected_hash
