"""Filesystem helpers shared by the installer and the key store.

These are small, but they encode two cross-platform lessons that are easy to
get wrong in one place and right in another:

* **Read as ``utf-8-sig``.** Windows editors and PowerShell's ``>`` /
  ``Set-Content -Encoding utf8`` write a UTF-8 BOM by default. A plain
  ``utf-8`` read leaves the BOM in the string, which makes ``json.loads``
  fail and turns a key file into ``"\\ufeffsk-..."``.
* **Write atomically with explicit newlines.** ``open(..., newline="")`` plus
  a temp file and ``os.replace`` gives byte-identical files on every OS and
  means a crash mid-write can never leave a truncated config or key.
"""

from __future__ import annotations

import os
import shutil
from pathlib import Path

# utf-8-sig strips a leading BOM when present and is otherwise identical to utf-8.
READ_ENCODING = "utf-8-sig"


def read_text(path: Path) -> str:
    """Read ``path`` as UTF-8, tolerating (and dropping) a leading BOM.

    Opened with ``newline=""`` so line endings come back exactly as they sit
    on disk. The default (universal newlines) would silently rewrite CRLF to
    LF, hiding a Windows-authored config's real endings from callers that need
    them — and making read/write behave differently per platform, which is the
    thing this module exists to prevent.
    """
    try:
        with open(path, encoding=READ_ENCODING, newline="") as handle:
            return handle.read()
    except OSError as exc:
        # Never fall back to "" here: callers need to tell a missing file from an
        # unreadable one, and silently yielding empty is what let an unreadable
        # config be overwritten. Attach the path once, so callers can translate
        # to their own error type without re-describing the failure.
        raise OSError(f"could not read {path}: {exc}") from exc


def atomic_write_text(path: Path, text: str) -> None:
    """Write ``text`` via a temp file + ``os.replace``.

    The temp file is created next to the target so the replace stays on one
    volume, which is what makes it atomic on POSIX and on Windows alike.
    """
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_name(f".{path.name}.tmp")
    try:
        with open(tmp, "w", encoding="utf-8", newline="") as handle:
            handle.write(text)
            handle.flush()
            os.fsync(handle.fileno())
        os.replace(tmp, path)
    except OSError:
        tmp.unlink(missing_ok=True)
        raise


def backup(path: Path) -> Path:
    """Copy ``path`` to ``<name>.bak`` beside it and return the backup path.

    Appends to the full name rather than rewriting the suffix, so names like
    ``.claude.json`` and extension-less files behave sanely.
    """
    target = path.with_name(path.name + ".bak")
    shutil.copy2(path, target)
    return target


def restrict(path: Path, mode: int) -> None:
    """Best-effort permission tightening.

    POSIX honours the mode bits. Windows has no equivalent — ``os.chmod`` only
    toggles the read-only flag — so confidentiality there rests on the
    per-user ACL of ``%USERPROFILE%``, and we skip rather than pretend.
    Failures are swallowed because ``chmod`` is also unsupported on some
    mounted filesystems (WSL ``/mnt/c`` under DrvFs, FAT32, many network
    shares) where refusing to store the key would be worse than storing it.
    """
    if os.name == "nt":
        return
    try:
        os.chmod(path, mode)
    except OSError:
        # Unsupported by the filesystem (DrvFs, FAT32, network shares): store
        # the key anyway rather than failing the setup step.
        pass
