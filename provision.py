import json
import os
import pathlib
import re
import subprocess
import tempfile


APP_NAME = "rpi-coreos"


def cache_dir():
    # from https://github.com/ActiveState/appdirs
    p = pathlib.Path(os.getenv('XDG_CACHE_HOME', os.path.expanduser('~/.cache'))) / APP_NAME
    p.mkdir(parents=True, exist_ok=True)
    return p


def coreos_installer_download(architecture, stream="stable"):
    # This is a bit of a hack.
    #
    # We run coreos-installer download twice- the first so the user gets feedback if downloading,
    # the second so we capture the output, which is the path to the downloaded file.
    coreos_installer("download", "-s", stream, "-a", architecture, "-C", cache_dir())
    out = coreos_installer("download", "-s", stream, "-a", architecture, "-C", cache_dir(), "--insecure", subprocess_options={"capture_output": True})
    return pathlib.Path(out.stdout.decode("UTF-8").strip())


def coreos_installer(*args, subprocess_options=None, sudo=False):
    if subprocess_options is None:
        subprocess_options = {}
    sudo_cmd = ("sudo",) if sudo else ()
    return subprocess.run(sudo_cmd + ("coreos-installer",) + args, check=True, **subprocess_options)


def coreos_installer_install(device, image):
    coreos_installer("install", "-f", image, device, sudo=True)


def umount(device):
    m = subprocess.run(["mount"], check=True, capture_output=True)
    mounts = m.stdout.decode("UTF-8").splitlines()
    mounts = [m.split()[0] for m in mounts]
    mounts = [m for m in mounts if m.startswith(device)]
    for m in mounts:
        subprocess.run(["umount", m], check=True)


def install(architecture, device, rpi_ver, stream="stable"):
    umount(device)
    f = coreos_installer_download(architecture, stream)
    coreos_installer_install(device, f)
    fedora_version = re.match(r"fedora-coreos-(\d+).*", f.name).group(1)
    root_dir = create_rpi_root(fedora_version, architecture)
    add_rpi_files(device, root_dir, rpi_ver)


def get_efi_part(device):
    parts = json.loads(subprocess.run(["lsblk", device, "-J", "-oLABEL,PATH"], check=True, capture_output=True).stdout)
    return [p["path"] for p in parts["blockdevices"] if p["label"] == "EFI-SYSTEM"][0]


def install_packages(packages, dest, fedora_version, architecture):
    subprocess.run(["podman", "run",
                    "-v", f"{dest}:/target",
                    "--security-opt", "label=disable",
                    "--pull", "always",
                    "--rm",
                    f"registry.fedoraproject.org/fedora:{fedora_version}",
                    "dnf",
                    "install",
                    "-y",
                    f"--forcearch={architecture}",
                    "--installroot", "/target",
                    "--release", fedora_version] + packages, check=True)


def create_rpi_root(fedora_version, architecture):
    root_dir = cache_dir() / f"fedora-{fedora_version}-{architecture}"
    root_dir.mkdir(parents=True, exist_ok=True)
    install_packages(["uboot-images-armv8", "bcm283x-firmware", "bcm283x-overlays", "bcm2835-firmware", "bcm2711-firmware"],
                     root_dir,
                     fedora_version,
                     architecture)
    return root_dir


def add_rpi_files(device, root_dir, rpi_ver):
    efi_part = get_efi_part(device)
    with tempfile.TemporaryDirectory() as tmpdir:
        tmpdir = pathlib.Path(tmpdir)
        subprocess.run(["sudo", "mount", efi_part, tmpdir], check=True)
        try:
            subprocess.run(["sudo", "cp", root_dir / f"usr/share/uboot/rpi_{rpi_ver}/u-boot.bin", tmpdir / f"rpi{rpi_ver}-u-boot.bin"], check=True)
            subprocess.run(["sudo", "rsync", "-avh", "--ignore-existing", f"{root_dir}/boot/efi/", f"{tmpdir}/"], check=False)
        finally:
            subprocess.run(["sudo", "umount", tmpdir], check=True)
