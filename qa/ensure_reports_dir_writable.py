#!/usr/bin/env python3
from __future__ import annotations

import argparse
import os
import shlex
import subprocess
from pathlib import Path


def _fix_owner(path: Path, *, host_uid: int, host_gid: int) -> None:
    container_path = f"/app/{path.as_posix()}"
    fix_cmd = f"mkdir -p {shlex.quote(container_path)} && chown -R {host_uid}:{host_gid} {shlex.quote(container_path)}"
    subprocess.run(["docker", "compose", "exec", "-T", "backend", "bash", "-lc", fix_cmd], check=True)


def main() -> int:
    parser = argparse.ArgumentParser(description="Asegura que QA_REPORTS_DIR sea escribible por el usuario local.")
    parser.add_argument("--reports-dir", required=True, help="Ruta configurada para QA_REPORTS_DIR")
    parser.add_argument("--host-uid", type=int, required=True, help="UID del usuario host")
    parser.add_argument("--host-gid", type=int, required=True, help="GID del usuario host")
    args = parser.parse_args()

    reports_dir = Path(args.reports_dir)

    try:
        reports_dir.mkdir(parents=True, exist_ok=True)
    except PermissionError:
        if reports_dir.is_absolute():
            raise SystemExit(f"[qa] reports dir is not writable: {reports_dir}")
        parent = reports_dir.parent if reports_dir.parent != Path("") else Path(".")
        print(f"[qa] fixing parent ownership for {parent}")
        _fix_owner(parent, host_uid=args.host_uid, host_gid=args.host_gid)
        reports_dir.mkdir(parents=True, exist_ok=True)

    if os.access(reports_dir, os.W_OK):
        return 0

    if reports_dir.is_absolute():
        raise SystemExit(f"[qa] reports dir is not writable: {reports_dir}")

    print(f"[qa] fixing report dir ownership for {reports_dir}")
    _fix_owner(reports_dir, host_uid=args.host_uid, host_gid=args.host_gid)

    if not os.access(reports_dir, os.W_OK):
        raise SystemExit(f"[qa] reports dir remains non-writable: {reports_dir}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
