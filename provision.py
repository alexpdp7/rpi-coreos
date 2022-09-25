import os
import pathlib
import subprocess


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


def install(architecture, device, stream="stable"):
    umount(device)
    f = coreos_installer_download(architecture, stream)
    coreos_installer_install(device, f)
