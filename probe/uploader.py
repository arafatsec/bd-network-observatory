"""Store-and-forward uploader: NOT IMPLEMENTED in v0.

v0 never sends data anywhere. Records stay in the local data/ folder.

TODO(store-and-forward, after the ethics review in docs/ETHICS.md):
  - upload records not yet sent, oldest first, once connectivity returns
  - remember what was sent (e.g. a per-file byte offset) so nothing is sent twice
  - publish only the fields described in docs/PROBE.md, identified by ASN and
    approximate region, never by host
"""

from pathlib import Path


def upload_pending(data_dir: Path) -> int:
    """Stub. Does nothing, sends nothing, and always returns 0 records uploaded."""
    del data_dir
    return 0
