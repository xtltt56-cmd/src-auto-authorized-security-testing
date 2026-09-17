"""Stable identity used to distinguish separate local project checkouts."""

import hashlib
import os
from pathlib import Path


def project_identity(root=None):
    path = Path(root or Path(__file__).resolve().parents[1]).resolve()
    normalized = os.path.normcase(str(path)).rstrip("\\/")
    return hashlib.sha256(normalized.encode("utf-8")).hexdigest()
