"""Verify the complete installed payload after Tauri's known NSIS marker patch.

Tauri CLI 2.10.1 patches UNK to NSS before bundling, then restores the build
output. See crates/tauri-bundler/src/bundle.rs at upstream commit
9b17a7aeae9a83222ffe829aa4e2d8a5ba6bed8c (tauri-cli-v2.10.1).
No other byte differences, including signatures, are accepted here.
"""

import hashlib
import json
import os
import re
import pathlib
import sys
import unittest

UNKNOWN = b"__TAURI_BUNDLE_TYPE_VAR_UNK"
NSIS = b"__TAURI_BUNDLE_TYPE_VAR_NSS"


def verify(built, installed):
    if not built.startswith(b"MZ") or not installed.startswith(b"MZ"):
        raise ValueError("Expected Windows executable payloads")
    if built.count(UNKNOWN) != 1:
        raise ValueError("Expected exactly one unpatched Tauri bundle marker")
    offset = built.index(UNKNOWN)
    expected = built[:offset] + NSIS + built[offset + len(UNKNOWN):]
    result = {
        "tauri_cli": "2.10.1",
        "upstream_commit": "9b17a7aeae9a83222ffe829aa4e2d8a5ba6bed8c",
        "allowed_transform": "single UNK to NSS bundle marker; no other differences",
        "built_sha256": hashlib.sha256(built).hexdigest(),
        "expected_nsis_sha256": hashlib.sha256(expected).hexdigest(),
        "installed_sha256": hashlib.sha256(installed).hexdigest(),
        "marker_offset": offset,
        "size": len(installed),
    }
    if installed != expected:
        raise ValueError("Installed bytes differ from exact Tauri NSIS payload: " + json.dumps(result))
    return result


def source_report(built, installed, source_sha):
    if not re.fullmatch(r"[0-9a-f]{40}", source_sha):
        raise ValueError("Missing exact source commit SHA")
    return {"source_sha": source_sha, **verify(built, installed)}


class PayloadTests(unittest.TestCase):
    def setUp(self):
        self.built = b"MZ\x00synthetic\xff" + UNKNOWN + b"\x00payload"
        self.installed = self.built.replace(UNKNOWN, NSIS)

    def test_known_marker_change(self):
        self.assertNotEqual(self.built, self.installed)
        self.assertEqual(verify(self.built, self.installed)["installed_sha256"],
                         hashlib.sha256(self.installed).hexdigest())

    def test_unpatched_installed_is_rejected(self):
        with self.assertRaises(ValueError):
            verify(self.built, self.built)

    def test_any_other_byte_change_is_rejected(self):
        for payload in (self.installed[:-1] + b"!", self.installed + b"signature",
                        self.installed[:-1], self.installed.replace(NSIS, UNKNOWN)):
            with self.subTest(payload=payload), self.assertRaises(ValueError):
                verify(self.built, payload)

    def test_missing_or_ambiguous_marker_is_rejected(self):
        for built in (self.installed, self.built + UNKNOWN):
            with self.subTest(built=built), self.assertRaises(ValueError):
                verify(built, self.installed)

    def test_source_sha_is_bound(self):
        sha = "1234567890abcdef1234567890abcdef12345678"
        self.assertEqual(source_report(self.built, self.installed, sha)["source_sha"], sha)

    def test_invalid_source_sha_is_rejected(self):
        for sha in ("", "main", "1234567"):
            with self.subTest(sha=sha), self.assertRaises(ValueError):
                source_report(self.built, self.installed, sha)

    def test_non_executable_is_rejected(self):
        with self.assertRaises(ValueError):
            verify(self.built[2:], self.installed)


if __name__ == "__main__":
    if sys.argv[1:] == ["--self-test"]:
        unittest.main(argv=[sys.argv[0]])
    elif len(sys.argv) == 4:
        result = source_report(pathlib.Path(sys.argv[1]).read_bytes(),
                               pathlib.Path(sys.argv[2]).read_bytes(),
                               os.environ.get("GITHUB_SHA", ""))
        pathlib.Path(sys.argv[3]).write_text(json.dumps(result, indent=2) + "\n", encoding="utf-8")
        print(json.dumps(result))
    else:
        raise SystemExit("Usage: verify-nsis-payload.py BUILT INSTALLED REPORT | --self-test")
