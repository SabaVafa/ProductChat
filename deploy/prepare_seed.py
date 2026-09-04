"""Build deploy/seed/ from the live backend data for the demo Docker image.

Copies the catalog DB + prebuilt Qdrant vectors that the Dockerfile bakes into
the image, and CLEARS the stored (encrypted) Mistral key from the DB copy so the
deployed container re-seeds it from the MISTRAL_API_KEY env var. That makes the
deploy independent of the local ENCRYPTION_KEY (no secret has to be reused).

Run with the backend STOPPED (so the SQLite/Qdrant files are quiescent):

    cd backend
    ../.venv/Scripts/python.exe ../deploy/prepare_seed.py

Output: deploy/seed/productchat.db and deploy/seed/qdrant_local/
"""
import os
import shutil
import sqlite3
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
REPO = os.path.dirname(HERE)
BACKEND = os.path.join(REPO, "backend")
SEED = os.path.join(HERE, "seed")

SRC_DB = os.path.join(BACKEND, "productchat.db")
SRC_QDRANT = os.path.join(BACKEND, "qdrant_local")


def _copy_qdrant(src: str, dst: str) -> None:
    # Skip the local-mode lock file so the copy isn't seen as owned by a process.
    shutil.copytree(
        src, dst,
        ignore=shutil.ignore_patterns(".lock", "*.tmp"),
    )


def main() -> int:
    if not os.path.exists(SRC_DB):
        print(f"ERROR: {SRC_DB} not found", file=sys.stderr)
        return 1
    if not os.path.isdir(SRC_QDRANT):
        print(f"ERROR: {SRC_QDRANT} not found", file=sys.stderr)
        return 1

    if os.path.isdir(SEED):
        shutil.rmtree(SEED)
    os.makedirs(SEED, exist_ok=True)

    # 1) DB copy, with the stored Mistral key cleared (reseeded from env on deploy).
    dst_db = os.path.join(SEED, "productchat.db")
    shutil.copy2(SRC_DB, dst_db)
    con = sqlite3.connect(dst_db)
    try:
        n = con.execute(
            "DELETE FROM settings WHERE category='mistral' AND key='api_key'"
        ).rowcount
        con.commit()
        con.execute("VACUUM")
    finally:
        con.close()
    print(f"DB copied -> seed/productchat.db (cleared {n} stored api_key row(s))")

    # 2) Qdrant vectors copy.
    dst_qdrant = os.path.join(SEED, "qdrant_local")
    _copy_qdrant(SRC_QDRANT, dst_qdrant)

    def _du(path: str) -> str:
        total = 0
        if os.path.isfile(path):
            total = os.path.getsize(path)
        else:
            for root, _dirs, files in os.walk(path):
                for f in files:
                    total += os.path.getsize(os.path.join(root, f))
        return f"{total/1_048_576:.1f} MB"

    print(f"Qdrant copied -> seed/qdrant_local ({_du(dst_qdrant)})")
    print(f"DB size: {_du(dst_db)}")
    print("Seed ready. Commit deploy/seed/ (or ship it as a build asset) so the "
          "Dockerfile can bake it in.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
