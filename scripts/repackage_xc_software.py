#!/usr/bin/env python3
"""Repackage an XC release with the pinned deployment tool for its target architecture."""

import argparse
import json
import os
import pathlib
import shutil
import stat
import subprocess
import sys
import tarfile
import tempfile


def regular_file(path):
    info = path.lstat()
    if not stat.S_ISREG(info.st_mode):
        raise ValueError("expected a regular file: {}".format(path))
    return path


def release_manifest(archive):
    with tarfile.open(archive, "r:gz") as payload:
        manifest_file = payload.extractfile("software/MANIFEST.json")
        if manifest_file is None:
            raise ValueError("release payload has no software manifest")
        return json.load(manifest_file)


def repackage(args):
    archive = regular_file(pathlib.Path(args.archive).resolve())
    stage = pathlib.Path(args.stage).resolve()
    tooling = pathlib.Path(args.tooling).resolve()
    installer = regular_file(pathlib.Path(args.installer).resolve())
    staged_installer = regular_file(stage / "tools/instance-deploy")
    manifest = release_manifest(archive)
    if (manifest["schema_version"] != 2 or manifest["product"] != "otg-go"
            or manifest["architecture"] != args.architecture or manifest["variant"] != "kylin-xc"
            or manifest["source_commit"] != args.release_sha):
        raise ValueError("original release identity does not match the XC request")
    if len(args.tooling_sha) != 40:
        raise ValueError("tooling commit must be a full pinned SHA")

    shutil.copyfile(installer, staged_installer)
    staged_installer.chmod(0o755)
    baseline = manifest["os_baseline"]["abi_limits"]
    with tempfile.TemporaryDirectory(prefix=args.architecture + "-repackage-", dir=archive.parent) as temporary:
        replacement = pathlib.Path(temporary) / archive.name
        command = [
            sys.executable, str(tooling / "scripts/software_payload.py"), "build",
            "--source-root", str(stage), "--output", str(replacement),
            "--product", manifest["product"], "--version", manifest["version"],
            "--architecture", manifest["architecture"], "--variant", manifest["variant"],
            "--source-commit", args.release_sha + "+" + args.tooling_sha,
            "--build-base", manifest["build_base"],
            "--data-migration", manifest["data_migration"]["mode"],
        ]
        for name in ("max_glibc", "max_glibcxx", "max_cxxabi", "max_gcc"):
            command.extend(("--" + name.replace("_", "-"), baseline[name]))
        env = os.environ.copy()
        env["SOURCE_DATE_EPOCH"] = args.source_date_epoch
        subprocess.run(command, check=True, env=env)
        subprocess.run(
            [sys.executable, str(tooling / "scripts/software_payload.py"), "verify",
             "--archive", str(replacement)],
            check=True,
        )
        actual = release_manifest(replacement)
        if actual["source_commit"] != args.release_sha + "+" + args.tooling_sha:
            raise ValueError("repackaged release lost its two-source identity")
        replacement_digest = replacement.with_name(replacement.name + ".sha256")
        os.replace(replacement, archive)
        os.replace(replacement_digest, archive.with_name(archive.name + ".sha256"))


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--archive", required=True)
    parser.add_argument("--architecture", choices=("amd64", "arm64"), required=True)
    parser.add_argument("--stage", required=True)
    parser.add_argument("--tooling", required=True)
    parser.add_argument("--installer", required=True)
    parser.add_argument("--release-sha", required=True)
    parser.add_argument("--tooling-sha", required=True)
    parser.add_argument("--source-date-epoch", required=True)
    args = parser.parse_args()
    try:
        repackage(args)
    except (OSError, ValueError, KeyError, tarfile.TarError, subprocess.CalledProcessError) as error:
        parser.exit(1, "XC release repackage failed: {}\n".format(error))


if __name__ == "__main__":
    main()
