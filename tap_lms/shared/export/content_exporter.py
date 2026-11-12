"""
shared/export/content_exporter.py

General LMS content-to-R2 export pipeline (videos, quizzes, units) is a
separate, pre-existing concern from the TapApp progress/submission work and
is intentionally left as a stub here. Fill in only when that pipeline is
actually being built/ported into this package.
"""

from __future__ import annotations


def export_content() -> None:
    raise NotImplementedError("content export pipeline is out of scope for this pass")