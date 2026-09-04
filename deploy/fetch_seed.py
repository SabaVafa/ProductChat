"""Download the demo seed tarball and extract it, at Docker BUILD time.

Keeps the ~5 MB seed out of the Git repo: it lives as a GitHub Release asset and
is fetched into the image during build. Stdlib only (no curl/tar needed in the
base image).

    python fetch_seed.py <SEED_URL> <DEST_DIR>

The tarball's members are productchat.db and qdrant_local/ at the root, so they
land directly in <DEST_DIR> (e.g. /data/productchat.db, /data/qdrant_local/).
"""
import io
import os
import sys
import tarfile
import urllib.request


def main() -> int:
    if len(sys.argv) != 3:
        print("usage: fetch_seed.py <SEED_URL> <DEST_DIR>", file=sys.stderr)
        return 2
    url, dest = sys.argv[1], sys.argv[2]
    os.makedirs(dest, exist_ok=True)
    print(f"Fetching seed: {url}")
    req = urllib.request.Request(url, headers={"User-Agent": "productchat-build"})
    with urllib.request.urlopen(req, timeout=120) as r:
        data = r.read()
    print(f"Downloaded {len(data)/1_048_576:.1f} MB; extracting to {dest}")
    with tarfile.open(fileobj=io.BytesIO(data), mode="r:gz") as tf:
        tf.extractall(dest)
    # Sanity: the DB must be present, or retrieval has no catalog.
    db = os.path.join(dest, "productchat.db")
    if not os.path.exists(db):
        print(f"ERROR: {db} missing after extract", file=sys.stderr)
        return 1
    print("Seed extracted OK")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
