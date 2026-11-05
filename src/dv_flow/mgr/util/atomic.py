"""Small atomic filesystem helpers (write-then-rename, symlink-then-replace)."""
import os
import tempfile
import uuid


def _umask() -> int:
    m = os.umask(0)
    os.umask(m)
    return m


def atomic_write_text(path: str, text: str, mode: int = 0o644):
    """Write ``text`` to ``path`` atomically: temp file in the same directory,
    fsync, then ``os.replace``. The temp file is removed on failure."""
    d = os.path.dirname(os.path.abspath(path))
    fd, tmp = tempfile.mkstemp(prefix=".%s.tmp." % os.path.basename(path), dir=d)
    try:
        os.fchmod(fd, mode & ~_umask())
        with os.fdopen(fd, "w") as fp:
            fp.write(text)
            fp.flush()
            os.fsync(fp.fileno())
        os.replace(tmp, path)
    except BaseException:
        try:
            os.unlink(tmp)
        except OSError:
            pass
        raise


def atomic_symlink(target: str, link_path: str):
    """Point ``link_path`` at ``target`` atomically. An existing link (or
    file) at ``link_path`` is replaced; an existing *directory* is not."""
    d = os.path.dirname(os.path.abspath(link_path))
    while True:
        tmp = os.path.join(d, ".%s.tmp.%d.%s" % (
            os.path.basename(link_path), os.getpid(), uuid.uuid4().hex[:8]))
        try:
            os.symlink(target, tmp)
            break
        except FileExistsError:
            continue
    try:
        os.replace(tmp, link_path)
    except BaseException:
        try:
            os.unlink(tmp)
        except OSError:
            pass
        raise
