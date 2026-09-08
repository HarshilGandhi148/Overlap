"""Create private local settings and optionally install the official Mac binary."""
import argparse
import hashlib
import os
from pathlib import Path
import platform
import secrets
import tarfile
import urllib.request
from core.services import ROOT

VERSION = "30.2"


def setup(download=False):
    env = ROOT / ".env"
    if not env.exists():
        with env.open("x") as handle:
            handle.write("TYPESENSE_HOST=127.0.0.1\nTYPESENSE_PORT=8108\nTYPESENSE_PROTOCOL=http\n"
                         f"TYPESENSE_API_KEY={secrets.token_urlsafe(32)}\nTYPESENSE_COLLECTION_PREFIX=overlap_local\n")
        env.chmod(0o600)
        print("Created .env with a private local key.")
    runtime = ROOT / ".runtime"
    runtime.mkdir(exist_ok=True)
    (runtime / "typesense-data").mkdir(exist_ok=True)
    tools_dir = ROOT / ".tools"
    tools_dir.mkdir(exist_ok=True)
    binary = tools_dir / "typesense-server"
    if download and not binary.exists():
        if platform.system() != "Darwin":
            raise RuntimeError("The bundled installer targets macOS. Use compose.yaml or an existing server on other platforms.")
        arch = "arm64" if platform.machine() == "arm64" else "amd64"
        url = f"https://dl.typesense.org/releases/{VERSION}/typesense-server-{VERSION}-darwin-{arch}.tar.gz"
        archive = tools_dir / f"typesense-{VERSION}-{arch}.tar.gz"
        print(f"Downloading official Typesense {VERSION} for {arch}…")
        urllib.request.urlretrieve(url, archive)
        with tarfile.open(archive) as tar:
            # Extract exactly the named regular files; never trust arbitrary archive paths.
            for name in ("typesense-server", "typesense-server.md5.txt"):
                member = tar.getmember(name)
                if not member.isfile():
                    raise RuntimeError("Unexpected archive member type")
                (tools_dir / name).write_bytes(tar.extractfile(member).read())
        print("Downloaded local server.")
    if binary.exists():
        checksum = tools_dir / "typesense-server.md5.txt"
        if checksum.exists():
            digest = hashlib.md5(binary.read_bytes(), usedforsecurity=False).hexdigest()
            if digest != checksum.read_text().strip().split()[0]:
                raise RuntimeError("The binary does not match its supplied checksum.")
        binary.chmod(0o755)
        print("Local server binary is ready.")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--download", action="store_true")
    setup(parser.parse_args().download)
