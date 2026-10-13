"""Spec management — list the extracted specs and mark one active.

A spec is a directory: `specs/<name>/` holding `spec.yaml` plus `pages/` and
`assets/`, exactly as `extract-spec` writes it.
"""

from __future__ import annotations

import sys
from pathlib import Path

_ACTIVE_FILE = ".active"


def _spec_names(specs_dir: str = "specs") -> list[str]:
    d = Path(specs_dir)
    if not d.is_dir():
        return []
    return sorted(s.name for s in d.iterdir()
                  if s.is_dir() and (s / "spec.yaml").exists())


def list_specs(specs_dir: str = "specs") -> list[str]:
    """Return the names of the extracted specs (no output)."""
    return _spec_names(specs_dir)


def select_spec(name: str, specs_dir: str = "specs") -> Path:
    """Mark a spec as the active one (writes specs/.active)."""
    if name not in _spec_names(specs_dir):
        available = _spec_names(specs_dir)
        print(f"Spec '{name}' not found in {specs_dir}/."
              + (f" Available: {', '.join(available)}" if available else ""),
              file=sys.stderr)
        raise FileNotFoundError(f"Spec '{name}' not found in {specs_dir}/")

    active = Path(specs_dir) / _ACTIVE_FILE
    active.write_text(name + "\n", encoding="utf-8")
    return active


def get_active_spec(specs_dir: str = "specs") -> str | None:
    """The active spec's name, or None when no spec has been selected."""
    active = Path(specs_dir) / _ACTIVE_FILE
    if not active.is_file():
        return None
    try:
        name = active.read_text(encoding="utf-8").strip()
    except OSError:
        return None
    return name or None


__all__ = ["list_specs", "select_spec", "get_active_spec"]
