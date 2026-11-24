"""Stage and verify the MIT-licensed M2M100 CTranslate2 weights without loading a model."""
import argparse
from contextlib import contextmanager
import hashlib
import os
from pathlib import Path
import sys
import tempfile
from urllib.request import Request, urlopen


REVISION = "e205afefce2fd6933a1dca3b92b5063894f2f2bb"
REPOSITORY = "auralmira/m2m100-418M-ct2-int8"
DESTINATION = "/var/lib/tcg-hub/models/m2m100-418m-int8"
FILES = {
    "config.json": (223, "8f6496adfc930cbfecbe8281112197705c488fab47d34b4829b06d7f478909af"),
    "shared_vocabulary.json": (2796509, "7eb5d0ff184c6095c7c10f9911c0aea492250abd12854f9c3d787c64b1c6397e"),
    "sentencepiece.bpe.model": (2423393, "d8f7c76ed2a5e0822be39f0a4f95a55eb19c78f4593ce609e2edbc2aea4d380a"),
    "model.bin": (490667752, "137949450f9cf691f3c92084f14123e82d05ecb23ac3cd688308ce1a95214572"),
}


def valid(path, expected):
    if path.is_symlink() or not path.is_file() or path.stat().st_size != expected[0]:
        return False
    with path.open("rb") as stream:
        digest = hashlib.sha256()
        while chunk := stream.read(1024 * 1024):
            digest.update(chunk)
        return digest.hexdigest() == expected[1]


@contextmanager
def lock_install(path):
    with path.open("a+b") as lock:
        try:
            if os.name == "nt":
                import msvcrt
                lock.seek(0, 2)
                if lock.tell() == 0:
                    lock.write(b"0")
                    lock.flush()
                lock.seek(0)
                msvcrt.locking(lock.fileno(), msvcrt.LK_NBLCK, 1)
            else:
                import fcntl
                fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
        except OSError as error:
            raise OSError("Another model installation is running.") from error
        yield


def stage_file(stage, name, source):
    size, expected_hash = FILES[name]
    if source:
        stream = (source / name).open("rb")
    else:
        url = f"https://huggingface.co/{REPOSITORY}/resolve/{REVISION}/{name}"
        stream = urlopen(Request(url, headers={"User-Agent": "TCGHub-Model-Setup/1"}), timeout=120)
    temp = stage / (name + ".download")
    try:
        temp.unlink(missing_ok=True)
        with stream, temp.open("xb") as output:
            digest = hashlib.sha256()
            received = 0
            while chunk := stream.read(1024 * 1024):
                received += len(chunk)
                if received > size:
                    raise ValueError(f"{name}: size exceeds the pinned model file")
                digest.update(chunk)
                output.write(chunk)
            if received != size or digest.hexdigest() != expected_hash:
                raise ValueError(f"{name}: model checksum or length mismatch")
        os.replace(temp, stage / name)
    finally:
        temp.unlink(missing_ok=True)


def install(destination, source=None):
    destination = destination.absolute()
    parent = destination.parent
    parent.mkdir(mode=0o700, parents=True, exist_ok=True)
    with lock_install(parent / f".{destination.name}.install.lock"):
        if destination.is_symlink() or (destination.exists() and not destination.is_dir()):
            raise ValueError("Model destination must be a private directory.")
        if all(valid(destination / name, expected) for name, expected in FILES.items()):
            return
        if destination.exists() and any(p.name not in FILES or p.is_symlink() or not p.is_file()
                                        for p in destination.iterdir()):
            raise ValueError("Model destination contains unrelated files. Choose a dedicated directory.")
        stage = parent / f".{destination.name}.{REVISION[:12]}.partial"
        if stage.is_symlink():
            raise ValueError("Model staging directory must be private.")
        stage.mkdir(mode=0o700, exist_ok=True)
        for member in stage.iterdir():
            if member.name.endswith(".download") and member.name[:-9] in FILES:
                member.unlink()
            elif member.name not in FILES or member.is_symlink() or not member.is_file():
                raise ValueError("Model staging directory contains unrelated files.")
        for name, expected in FILES.items():
            staged = stage / name
            if valid(staged, expected):
                continue
            # Reuse valid files from an incomplete destination; neither the source nor the
            # previous installation is changed while downloading and checking other files.
            local_source = destination if valid(destination / name, expected) else source
            stage_file(stage, name, local_source)
        old = None
        if destination.exists():
            old = Path(tempfile.mkdtemp(dir=parent, prefix=f".{destination.name}.previous-"))
            old.rmdir()
            destination.rename(old)
        try:
            stage.rename(destination)
        except OSError:
            if old is not None:
                old.rename(destination)
            raise
        if old is not None:
            for member in old.iterdir():
                member.unlink()
            old.rmdir()


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--destination", type=Path, default=Path(DESTINATION))
    parser.add_argument("--source", type=Path, help="offline directory containing the four pinned model files")
    args = parser.parse_args()
    try:
        install(args.destination, args.source)
    except (OSError, ValueError) as error:
        sys.exit(f"Translation model installation failed: {error}")
    print(f"Verified {REPOSITORY}@{REVISION} in {args.destination}")
