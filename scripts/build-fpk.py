#!/usr/bin/env python3
"""Build personal-use fnOS FPK packages for Bootimus."""

from __future__ import annotations

import argparse
import hashlib
import io
import json
import os
import shutil
import tarfile
import tempfile
import urllib.request
from pathlib import Path


APP_NAME = "App.Native.Bootimus"
BINARY_NAME = "bootimus"
DISPLAY_NAME = "Bootimus"
APP_LAUNCH_NAME = "App.Native.Bootimus.Web"
ADMIN_PORT = 8081
DATA_SHARE_NAME = "bootimus"
DEFAULT_CREDENTIALS_TEXT = "默认账号 admin；初始密码首次启动随机生成，请在应用文件/bootimus/logs/bootimus.log 查看。"
UPSTREAM_URL = "https://github.com/garybowers/bootimus"

ASSETS = {
    "x86": {
        "asset_name": "bootimus-linux-amd64",
        "url": "https://github.com/garybowers/bootimus/releases/download/v0.1.70/bootimus-linux-amd64",
        "sha256": "bd6bb20064a96e74fb21604372041b7d1ca6ece905677a5ca65db0deda60428b",
    },
    "arm": {
        "asset_name": "bootimus-linux-arm64",
        "url": "https://github.com/garybowers/bootimus/releases/download/v0.1.70/bootimus-linux-arm64",
        "sha256": "9ae32dc6caa0800916c75cc46a646c88b38bdf0831b9529df2b725200640bc92",
    },
}

ROOT = Path(__file__).resolve().parents[1]
SOURCE_DIR = ROOT / "fnos-appstore-bootimus"
DOWNLOADS_DIR = ROOT / ".tmp" / "downloads"
DIST_DIR = ROOT / "dist"


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as fh:
        for chunk in iter(lambda: fh.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def download_asset(downloads_dir: Path, asset_name: str, url: str, sha256: str) -> Path:
    downloads_dir.mkdir(parents=True, exist_ok=True)
    target = downloads_dir / asset_name
    if target.exists() and sha256_file(target) == sha256:
        return target

    tmp_target = target.with_suffix(".download")
    if tmp_target.exists():
        tmp_target.unlink()

    with urllib.request.urlopen(url, timeout=120) as response, tmp_target.open("wb") as out:
        shutil.copyfileobj(response, out)

    actual = sha256_file(tmp_target)
    if actual != sha256:
        tmp_target.unlink(missing_ok=True)
        raise RuntimeError(f"{asset_name} sha256 mismatch: expected {sha256}, got {actual}")

    tmp_target.replace(target)
    return target


def normalize_tarinfo(info: tarfile.TarInfo, mode: int) -> tarfile.TarInfo:
    info.uid = 0
    info.gid = 0
    info.uname = "root"
    info.gname = "root"
    info.mtime = 0
    info.mode = mode
    return info


def tar_add_file(tar: tarfile.TarFile, source: Path, arcname: str, mode: int) -> None:
    info = tar.gettarinfo(str(source), arcname)
    normalize_tarinfo(info, mode)
    with source.open("rb") as fh:
        tar.addfile(info, fh)


def tar_add_bytes(tar: tarfile.TarFile, content: bytes, arcname: str, mode: int) -> None:
    info = tarfile.TarInfo(arcname)
    info.size = len(content)
    normalize_tarinfo(info, mode)
    tar.addfile(info, io.BytesIO(content))


def tar_add_directory(tar: tarfile.TarFile, arcname: str) -> None:
    info = tarfile.TarInfo(arcname.rstrip("/"))
    info.type = tarfile.DIRTYPE
    normalize_tarinfo(info, 0o755)
    tar.addfile(info)


def iter_files(root: Path):
    for path in sorted(root.rglob("*")):
        if path.is_file():
            yield path


def iter_dirs(root: Path):
    for path in sorted(root.rglob("*")):
        if path.is_dir():
            yield path


def app_file_mode(path: Path) -> int:
    if path.name == BINARY_NAME:
        return 0o755
    return 0o644


def outer_file_mode(path: Path) -> int:
    rel = path.as_posix()
    if rel.startswith("cmd/"):
        return 0o755
    return 0o644


def md5_bytes(content: bytes) -> str:
    return hashlib.md5(content).hexdigest()


def manifest_line(key: str, value: str) -> str:
    return f"{key:<22}= {value}"


def render_manifest(version: str, platform: str, app_tgz: bytes) -> str:
    return "\n".join(
        [
            manifest_line("appname", APP_NAME),
            manifest_line("version", version),
            manifest_line("display_name", DISPLAY_NAME),
            manifest_line("desc", f"PXE/HTTP 启动维护服务。{DEFAULT_CREDENTIALS_TEXT}"),
            manifest_line("platform", platform),
            manifest_line("source", "thirdparty"),
            manifest_line("maintainer", "garybowers"),
            manifest_line("maintainer_url", UPSTREAM_URL),
            manifest_line("distributor", "local"),
            manifest_line("distributor_url", UPSTREAM_URL),
            manifest_line("os_min_version", "0.9.0"),
            manifest_line("ctl_stop", "true"),
            manifest_line("desktop_uidir", "ui"),
            manifest_line("desktop_applaunchname", APP_LAUNCH_NAME),
            manifest_line("service_port", str(ADMIN_PORT)),
            manifest_line("checkport", "false"),
            manifest_line("disable_authorization_path", "true"),
            manifest_line("changelog", "Bootimus v0.1.70 个人自用飞牛包。"),
            manifest_line("checksum", md5_bytes(app_tgz)),
            "",
        ]
    )


def render_ui_config() -> str:
    data = {
        ".url": {
            APP_LAUNCH_NAME: {
                "title": DISPLAY_NAME,
                "desc": "Bootimus PXE/HTTP 启动维护服务管理界面。",
                "icon": "images/{0}.png",
                "type": "iframe",
                "protocol": "http",
                "port": str(ADMIN_PORT),
                "url": "/",
                "allUsers": False,
                "noDisplay": False,
            }
        }
    }
    return json.dumps(data, indent=2, ensure_ascii=False) + "\n"


def expected_resource() -> dict:
    return {
        "port": ADMIN_PORT,
        "data-share": {
            "shares": [
                {
                    "name": DATA_SHARE_NAME,
                    "permission": {
                        "rw": [APP_NAME],
                    },
                }
            ]
        },
    }


def build_app_tgz(source_dir: Path, binary_path: Path) -> bytes:
    app_root = source_dir / "app"
    if not app_root.is_dir():
        raise FileNotFoundError(f"missing app source directory: {app_root}")

    fileobj = io.BytesIO()
    with tarfile.open(fileobj=fileobj, mode="w:gz", format=tarfile.PAX_FORMAT) as app_tar:
        tar_add_file(app_tar, binary_path, BINARY_NAME, 0o755)
        for path in iter_dirs(app_root):
            rel = path.relative_to(app_root).as_posix()
            tar_add_directory(app_tar, rel)
        for path in iter_files(app_root):
            rel = path.relative_to(app_root).as_posix()
            if rel == "ui/config":
                tar_add_bytes(app_tar, render_ui_config().encode("utf-8"), rel, 0o644)
            else:
                tar_add_file(app_tar, path, rel, app_file_mode(path))
        tar_add_directory(app_tar, "config")
        for rel in ["config/privilege", "config/resource"]:
            path = source_dir / rel
            tar_add_file(app_tar, path, rel, outer_file_mode(Path(rel)))
    return fileobj.getvalue()


def validate_source(source_dir: Path) -> None:
    required = [
        "cmd/main",
        "cmd/install_init",
        "cmd/install_callback",
        "cmd/uninstall_init",
        "cmd/uninstall_callback",
        "cmd/upgrade_init",
        "cmd/upgrade_callback",
        "cmd/config_init",
        "cmd/config_callback",
        "config/privilege",
        "config/resource",
        "wizard/install",
        "wizard/uninstall",
        "LICENSE",
        "ICON.PNG",
        "ICON_256.PNG",
        "app/bootimus.example.yaml",
        "app/THIRD_PARTY_NOTICES.md",
        "app/ui/config",
        "app/ui/images/64.png",
        "app/ui/images/256.png",
    ]
    missing = [rel for rel in required if not (source_dir / rel).is_file()]
    if missing:
        raise FileNotFoundError("missing package source files: " + ", ".join(missing))

    privilege = json.loads((source_dir / "config" / "privilege").read_text(encoding="utf-8"))
    if privilege.get("defaults", {}).get("run-as") != "root":
        raise ValueError("config/privilege must set defaults.run-as to root")
    if privilege.get("username") != APP_NAME or privilege.get("groupname") != APP_NAME:
        raise ValueError("config/privilege must use App.Native.Bootimus username and groupname")

    resource = json.loads((source_dir / "config" / "resource").read_text(encoding="utf-8"))
    if resource != expected_resource():
        raise ValueError("config/resource must declare the Bootimus admin port and bootimus data-share")

    wizard_install = json.loads((source_dir / "wizard" / "install").read_text(encoding="utf-8"))
    if len(wizard_install) < 2 or wizard_install[0].get("stepTitle") != "Bootimus 配置" or wizard_install[1].get("stepTitle") != "网络配置":
        raise ValueError("wizard/install must place network settings on the second step")
    wizard_text = json.dumps(wizard_install, ensure_ascii=False)
    first_step_text = json.dumps(wizard_install[0], ensure_ascii=False)
    second_step_text = json.dumps(wizard_install[1], ensure_ascii=False)
    if "wizard_bootimus_network_mode" in first_step_text or "wizard_bootimus_network_mode" not in second_step_text:
        raise ValueError("wizard/install network fields must be on the second step")
    network_mode_items = [
        item for item in wizard_install[1].get("items", [])
        if item.get("field") == "wizard_bootimus_network_mode"
    ]
    network_mode_values = [
        option.get("value") for option in network_mode_items[0].get("options", [])
    ] if network_mode_items else []
    if network_mode_values != ["host", "macvlan", "ipvlan"]:
        raise ValueError("wizard/install network mode options must be ordered host, macvlan, ipvlan")
    for marker in [
        "wizard_bootimus_iso_dir",
        "wizard_bootimus_admin_password",
        "wizard_bootimus_network_mode",
        "wizard_bootimus_network_parent",
        "wizard_bootimus_network_address",
        "wizard_bootimus_network_gateway",
        "独立 IP",
        "DHCP",
        "ISO",
        "应用文件",
        DEFAULT_CREDENTIALS_TEXT,
    ]:
        if marker not in wizard_text:
            raise ValueError(f"wizard/install must contain {marker}")

    license_text = (source_dir / "LICENSE").read_text(encoding="utf-8")
    for marker in ["个人自用", "开源许可证"]:
        if marker not in license_text:
            raise ValueError(f"LICENSE must contain Chinese marker {marker}")
    for forbidden in ["provided for personal use", "redistributed under", "Apache License"]:
        if forbidden in license_text:
            raise ValueError(f"LICENSE must not contain English marker {forbidden}")

    install_callback_text = (source_dir / "cmd" / "install_callback").read_text(encoding="utf-8")
    for marker in [
        "wizard_bootimus_network_mode",
        "wizard_bootimus_network_parent",
        "wizard_bootimus_network_address",
        "wizard_bootimus_network_gateway",
        "BOOTIMUS_NETWORK_MODE",
        "BOOTIMUS_NETWORK_PARENT",
        "BOOTIMUS_NETWORK_ADDRESS",
        "BOOTIMUS_NETWORK_GATEWAY",
        "BOOTIMUS_NETWORK_DHCP",
        "wizard raw network values",
        'wizard_network_mode="macvlan"',
    ]:
        if marker not in install_callback_text:
            raise ValueError(f"cmd/install_callback must contain {marker}")

    main_text = (source_dir / "cmd" / "main").read_text(encoding="utf-8")
    for marker in [
        "BOOTIMUS_NETWORK_MODE",
        "BOOTIMUS_NETNS",
        "ip netns add",
        "type ipvlan mode l2",
        "type macvlan mode bridge",
        "ip netns exec",
        "BOOTIMUS_LAUNCH_PROXY_PID_FILE",
        "BOOTIMUS_NETWORK_WATCHER_PID_FILE",
        "start_launch_redirect",
        "start_network_watcher",
        "stop_network_watcher",
        "network watcher detected IP change",
        "network watcher restarting Bootimus",
        "bootimus_service_ip",
        "BOOTIMUS_NETWORK_DHCP",
        "run_network_dhcp",
        "udhcpc",
        "dhclient",
        "detect_default_parent_interface",
        "ip route get",
        "lifecycle_log",
        "run_with_timeout",
        "start_app entered",
        "prepare_network_namespace",
        "DHCP uses macvlan",
        "python timeout fallback",
        "sync_external_iso_files",
        "mount_external_iso_files",
        "unmount_external_iso_files",
        "external_iso_mount_target_from_marker",
        "External ISO directory is read-only",
    ]:
        if marker not in main_text:
            raise ValueError(f"cmd/main must contain {marker}")
    if "falling back to host network" in main_text:
        raise ValueError("cmd/main must not downgrade independent IP mode to host when address is empty")
    if 'mount --bind "${BOOTIMUS_ISO_DIR}" "${BOOTIMUS_INTERNAL_ISO_DIR}"' in main_text:
        raise ValueError("cmd/main must bind-mount only ISO files, not the whole external ISO directory")

    wizard_uninstall = json.loads((source_dir / "wizard" / "uninstall").read_text(encoding="utf-8"))
    wizard_uninstall_text = json.dumps(wizard_uninstall, ensure_ascii=False)
    for marker in ["wizard_uninstall_data_action", "keep_all", "delete_all", "保留用户数据", "清除全部数据", "保留 ISO 目录"]:
        if marker not in wizard_uninstall_text:
            raise ValueError(f"wizard/uninstall must contain {marker}")

    uninstall_callback_text = (source_dir / "cmd" / "uninstall_callback").read_text(encoding="utf-8")
    for marker in [
        "wizard_uninstall_data_action",
        "keep_all",
        "delete_all",
        "safe_delete_tree()",
        "unmount_external_iso_files",
        "preserving bootimus ISO/data directory",
    ]:
        if marker not in uninstall_callback_text:
            raise ValueError(f"cmd/uninstall_callback must contain {marker}")
    for forbidden in ["load_saved_bootimus_data_dir()", "BOOTIMUS_DATA_DIR"]:
        if forbidden in uninstall_callback_text:
            raise ValueError(f"cmd/uninstall_callback must not contain {forbidden}")


def build_package(
    source_dir: Path,
    downloads_dir: Path,
    dist_dir: Path,
    version: str,
    platform: str,
    asset_name: str,
) -> Path:
    source_dir = Path(source_dir)
    downloads_dir = Path(downloads_dir)
    dist_dir = Path(dist_dir)

    validate_source(source_dir)
    binary_path = downloads_dir / asset_name
    if not binary_path.is_file():
        raise FileNotFoundError(f"missing Bootimus binary: {binary_path}")

    dist_dir.mkdir(parents=True, exist_ok=True)
    package_path = dist_dir / f"{APP_NAME}_{version}_{platform}.fpk"

    app_tgz = build_app_tgz(source_dir, binary_path)
    manifest = render_manifest(version, platform, app_tgz).encode("utf-8")

    with tarfile.open(package_path, mode="w:gz", format=tarfile.PAX_FORMAT) as outer:
        tar_add_bytes(outer, manifest, "manifest", 0o644)
        tar_add_bytes(outer, app_tgz, "app.tgz", 0o644)
        tar_add_directory(outer, "cmd")
        for path in iter_files(source_dir / "cmd"):
            rel = path.relative_to(source_dir).as_posix()
            tar_add_file(outer, path, rel, outer_file_mode(Path(rel)))
        tar_add_directory(outer, "config")
        for rel in ["config/privilege", "config/resource", "LICENSE", "ICON.PNG", "ICON_256.PNG"]:
            path = source_dir / rel
            tar_add_file(outer, path, rel, outer_file_mode(Path(rel)))
        tar_add_directory(outer, "wizard")
        for path in iter_files(source_dir / "wizard"):
            rel = path.relative_to(source_dir).as_posix()
            tar_add_file(outer, path, rel, outer_file_mode(Path(rel)))

    validate_fpk(package_path, platform)
    return package_path


def validate_fpk(package_path: Path, platform: str) -> None:
    if package_path.read_bytes()[:2] != b"\x1f\x8b":
        raise RuntimeError(f"{package_path} is not a gzip tar")

    with tarfile.open(package_path, "r:gz") as outer:
        names = set(outer.getnames())
        required = {
            "manifest",
            "app.tgz",
            "cmd",
            "cmd/main",
            "config",
            "config/privilege",
            "config/resource",
            "wizard",
            "wizard/install",
            "wizard/uninstall",
            "LICENSE",
            "ICON.PNG",
            "ICON_256.PNG",
        }
        missing = required - names
        if missing:
            raise RuntimeError(f"{package_path} missing outer members: {sorted(missing)}")
        if outer.getmember("cmd/main").mode != 0o755:
            raise RuntimeError("cmd/main is not executable")
        resource = json.loads(outer.extractfile("config/resource").read().decode("utf-8"))
        if resource != expected_resource():
            raise RuntimeError("config/resource does not declare bootimus data-share")
        wizard_data = json.loads(outer.extractfile("wizard/install").read().decode("utf-8"))
        if len(wizard_data) < 2 or wizard_data[0].get("stepTitle") != "Bootimus 配置" or wizard_data[1].get("stepTitle") != "网络配置":
            raise RuntimeError("wizard/install must place network settings on the second step")
        wizard_text = json.dumps(wizard_data, ensure_ascii=False)
        first_step_text = json.dumps(wizard_data[0], ensure_ascii=False)
        second_step_text = json.dumps(wizard_data[1], ensure_ascii=False)
        if "wizard_bootimus_network_mode" in first_step_text or "wizard_bootimus_network_mode" not in second_step_text:
            raise RuntimeError("wizard/install network fields must be on the second step")
        for marker in [
            "wizard_bootimus_iso_dir",
            "wizard_bootimus_admin_password",
            "wizard_bootimus_network_mode",
            "wizard_bootimus_network_parent",
            "wizard_bootimus_network_address",
            "wizard_bootimus_network_gateway",
            "独立 IP",
            "DHCP",
            "ISO",
            "应用文件",
            DEFAULT_CREDENTIALS_TEXT,
        ]:
            if marker not in wizard_text:
                raise RuntimeError(f"wizard/install missing {marker}")
        wizard_uninstall_data = json.loads(outer.extractfile("wizard/uninstall").read().decode("utf-8"))
        wizard_uninstall_text = json.dumps(wizard_uninstall_data, ensure_ascii=False)
        for marker in ["wizard_uninstall_data_action", "keep_all", "delete_all", "保留用户数据", "清除全部数据", "保留 ISO 目录"]:
            if marker not in wizard_uninstall_text:
                raise RuntimeError(f"wizard/uninstall missing {marker}")
        manifest = outer.extractfile("manifest").read().decode("utf-8")
        app_tgz = outer.extractfile("app.tgz").read()
        for marker in [
            "appname               = App.Native.Bootimus",
            f"platform              = {platform}",
            f"desc                  = PXE/HTTP 启动维护服务。{DEFAULT_CREDENTIALS_TEXT}",
            "source                = thirdparty",
            "maintainer_url        = https://github.com/garybowers/bootimus",
            "distributor_url       = https://github.com/garybowers/bootimus",
            "os_min_version        = 0.9.0",
            "ctl_stop              = true",
            "desktop_uidir         = ui",
            "desktop_applaunchname = App.Native.Bootimus.Web",
            "service_port          = 8081",
            "checkport             = false",
            "changelog             = Bootimus v0.1.70 个人自用飞牛包。",
        ]:
            if marker not in manifest:
                raise RuntimeError(f"manifest missing {marker}")
        if "install_type=root" in manifest:
            raise RuntimeError("manifest must not contain install_type=root")
        if manifest_line("checksum", md5_bytes(app_tgz)) not in manifest:
            raise RuntimeError("manifest checksum does not match app.tgz")
        license_text = outer.extractfile("LICENSE").read().decode("utf-8")
        for marker in ["个人自用", "开源许可证"]:
            if marker not in license_text:
                raise RuntimeError(f"LICENSE missing Chinese marker {marker}")
        for forbidden in ["provided for personal use", "redistributed under", "Apache License"]:
            if forbidden in license_text:
                raise RuntimeError(f"LICENSE must not contain English marker {forbidden}")

    with tarfile.open(fileobj=io.BytesIO(app_tgz), mode="r:gz") as app_tar:
        names = set(app_tar.getnames())
        required = {
            "bootimus",
            "bootimus.example.yaml",
            "THIRD_PARTY_NOTICES.md",
            "ui",
            "ui/config",
            "ui/images",
            "ui/images/64.png",
            "ui/images/256.png",
            "config",
            "config/privilege",
            "config/resource",
        }
        missing = required - names
        if missing:
            raise RuntimeError(f"{package_path} missing app.tgz members: {sorted(missing)}")
        if "app/bootimus" in names:
            raise RuntimeError("app.tgz must not contain nested app/bootimus")
        if app_tar.getmember("bootimus").mode != 0o755:
            raise RuntimeError("app.tgz bootimus is not executable")
        ui_config = app_tar.extractfile("ui/config").read().decode("utf-8")
        for marker in ["App.Native.Bootimus.Web", '"port": "8081"', '"noDisplay": false']:
            if marker not in ui_config:
                raise RuntimeError(f"ui/config missing {marker}")


def write_checksums(paths: list[Path], dist_dir: Path) -> Path:
    checksum_path = dist_dir / "SHA256SUMS.txt"
    lines = [f"{sha256_file(path)}  {path.name}" for path in sorted(paths)]
    checksum_path.write_text("\n".join(lines) + "\n", encoding="utf-8")
    return checksum_path


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--version", default="0.1.70-1")
    parser.add_argument("--platform", choices=["x86", "arm", "all"], default="all")
    parser.add_argument("--source-dir", type=Path, default=SOURCE_DIR)
    parser.add_argument("--downloads-dir", type=Path, default=DOWNLOADS_DIR)
    parser.add_argument("--dist-dir", type=Path, default=DIST_DIR)
    parser.add_argument("--skip-download", action="store_true", help="Use existing files in downloads-dir")
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    platforms = ["x86", "arm"] if args.platform == "all" else [args.platform]
    built: list[Path] = []

    for platform in platforms:
        asset = ASSETS[platform]
        if not args.skip_download:
            download_asset(args.downloads_dir, asset["asset_name"], asset["url"], asset["sha256"])
        built.append(
            build_package(
                source_dir=args.source_dir,
                downloads_dir=args.downloads_dir,
                dist_dir=args.dist_dir,
                version=args.version,
                platform=platform,
                asset_name=asset["asset_name"],
            )
        )

    checksum_path = write_checksums(built, args.dist_dir)
    for path in built:
        print(f"built {path} sha256={sha256_file(path)}")
    print(f"wrote {checksum_path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
