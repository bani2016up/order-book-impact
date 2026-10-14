"""Smoke the actual extension; a Python replacement cannot satisfy this test."""
import importlib.machinery

from ofi_pipeline import _native, version


def test_compiled_extension():
    assert any(_native.__file__.endswith(s) for s in importlib.machinery.EXTENSION_SUFFIXES)
    assert version() == "0.1.0"
