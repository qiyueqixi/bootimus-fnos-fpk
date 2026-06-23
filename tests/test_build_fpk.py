import io
import json
import tarfile
import tempfile
import unittest
from pathlib import Path

import importlib.util


ROOT = Path(__file__).resolve().parents[1]
BUILD_SCRIPT = ROOT / "scripts" / "build-fpk.py"
DEFAULT_CREDENTIALS_TEXT = "默认账号 admin；初始密码首次启动随机生成，请在应用文件/bootimus/logs/bootimus.log 查看。"


def load_build_module():
    spec = importlib.util.spec_from_file_location("build_fpk", BUILD_SCRIPT)
    module = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    spec.loader.exec_module(module)
    return module


def make_file(path: Path, content: bytes) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(content)


def expected_resource() -> dict:
    return {
        "port": 8081,
        "data-share": {
            "shares": [
                {
                    "name": "bootimus",
                    "permission": {
                        "rw": ["App.Native.Bootimus"],
                    },
                }
            ]
        },
    }


class BuildFpkTests(unittest.TestCase):
    def test_build_package_preserves_fnos_layout_and_modes(self):
        build_fpk = load_build_module()

        with tempfile.TemporaryDirectory() as tmp:
            tmp_path = Path(tmp)
            source = tmp_path / "source"
            downloads = tmp_path / "downloads"
            dist = tmp_path / "dist"

            make_file(
                source / "cmd" / "main",
                b"""#!/bin/sh
# BOOTIMUS_NETWORK_MODE
# BOOTIMUS_NETNS
# ip netns add
# type ipvlan mode l2
# type macvlan mode bridge
# ip netns exec
# BOOTIMUS_LAUNCH_PROXY_PID_FILE
# BOOTIMUS_NETWORK_WATCHER_PID_FILE
# start_launch_redirect
# start_python_launch_redirect
# do_HEAD
# wait_for_launch_redirect_pid
# start_network_watcher
# stop_network_watcher
# network watcher detected IP change
# network watcher restarting Bootimus
# bootimus_service_ip
# BOOTIMUS_NETWORK_DHCP
# run_network_dhcp
# udhcpc
# dhclient
# detect_default_parent_interface
# ip route get
# wizard raw network values
# lifecycle_log
# run_with_timeout
# start_app entered
# prepare_network_namespace
# DHCP uses macvlan
# python timeout fallback
# normalize_windows_wimboot_params
# wimboot rawbcd compatibility
# sqlite3.connect(db_path)
# UPDATE distro_profiles
# UPDATE images
# REPLACE
# rawbcd
# Windows wimboot boot_params normalized
# start_app normalized Windows wimboot params
# sync_external_iso_files
# mount_external_iso_files
# unmount_external_iso_files
# external_iso_mount_target_from_marker
# External ISO directory is read-only
echo ok
""",
            )
            for hook in [
                "install_init",
                "install_callback",
                "uninstall_init",
                "upgrade_init",
                "upgrade_callback",
                "config_init",
                "config_callback",
            ]:
                if hook == "install_callback":
                    make_file(
                        source / "cmd" / hook,
                        b"""#!/bin/sh
# wizard_bootimus_network_mode
# wizard_bootimus_network_parent
# wizard_bootimus_network_address
# wizard_bootimus_network_gateway
# BOOTIMUS_NETWORK_MODE
# BOOTIMUS_NETWORK_PARENT
# BOOTIMUS_NETWORK_ADDRESS
# BOOTIMUS_NETWORK_GATEWAY
# BOOTIMUS_NETWORK_DHCP
# detect_default_parent_interface
# wizard raw network values
# wizard_network_mode="macvlan"
exit 0
""",
                    )
                else:
                    make_file(source / "cmd" / hook, b"#!/bin/sh\nexit 0\n")
            make_file(
                source / "cmd" / "uninstall_callback",
                b"""#!/bin/sh
# wizard_uninstall_data_action
# keep_all
# delete_all
# safe_delete_tree()
# unmount_external_iso_files
# preserving bootimus ISO/data directory
exit 0
""",
            )
            make_file(
                source / "config" / "privilege",
                b'{"defaults":{"run-as":"root"},"username":"App.Native.Bootimus","groupname":"App.Native.Bootimus"}\n',
            )
            make_file(source / "config" / "resource", json.dumps(expected_resource()).encode("utf-8") + b"\n")
            make_file(
                source / "wizard" / "install",
                json.dumps(
                    [
                        {
                            "stepTitle": "Bootimus 配置",
                            "items": [
                                {
                                    "type": "tips",
                                    "helpText": f"只填写 ISO 镜像目录；数据库、日志和运行文件保存在应用文件。{DEFAULT_CREDENTIALS_TEXT}",
                                },
                                {
                                    "type": "text",
                                    "field": "wizard_bootimus_iso_dir",
                                    "label": "ISO 镜像目录",
                                },
                                {
                                    "type": "password",
                                    "field": "wizard_bootimus_admin_password",
                                    "label": "admin 初始密码",
                                },
                            ],
                        },
                        {
                            "stepTitle": "网络配置",
                            "items": [
                                {
                                    "type": "select",
                                    "field": "wizard_bootimus_network_mode",
                                    "label": "网络模式",
                                    "helpText": "独立 IP/CIDR 留空时自动走 DHCP。",
                                    "options": [
                                        {"label": "使用宿主机网络", "value": "host"},
                                        {"label": "独立 IP（macvlan）", "value": "macvlan"},
                                        {"label": "独立 IP（ipvlan）", "value": "ipvlan"},
                                    ],
                                },
                                {
                                    "type": "text",
                                    "field": "wizard_bootimus_network_parent",
                                    "label": "父网卡",
                                },
                                {
                                    "type": "text",
                                    "field": "wizard_bootimus_network_address",
                                    "label": "独立 IP/CIDR",
                                },
                                {
                                    "type": "text",
                                    "field": "wizard_bootimus_network_gateway",
                                    "label": "网关",
                                },
                            ],
                        },
                    ]
                ).encode("utf-8")
                + b"\n",
            )
            make_file(
                source / "wizard" / "uninstall",
                json.dumps(
                    [
                        {
                            "stepTitle": "Uninstall data",
                            "items": [
                                {
                                    "type": "radio",
                                    "field": "wizard_uninstall_data_action",
                                    "initValue": "keep_all",
                                    "options": [
                                        {"label": "保留用户数据", "value": "keep_all"},
                                        {"label": "清除全部数据（保留 ISO 目录）", "value": "delete_all"},
                                    ],
                                }
                            ],
                        }
                    ]
                ).encode("utf-8")
                + b"\n",
            )
            make_file(source / "LICENSE", "Bootimus 飞牛包的元数据和生命周期脚本仅供个人自用。\n\nBootimus 本体按 Apache 2.0 开源许可证重新分发，来源：\nhttps://github.com/garybowers/bootimus\n".encode("utf-8"))
            make_file(source / "ICON.PNG", b"icon64\n")
            make_file(source / "ICON_256.PNG", b"icon256\n")
            make_file(source / "app" / "bootimus.example.yaml", b"admin_port: 8081\n")
            make_file(source / "app" / "THIRD_PARTY_NOTICES.md", b"notices\n")
            make_file(source / "app" / "ui" / "config", b'{" .url": {}}\n')
            make_file(source / "app" / "ui" / "images" / "64.png", b"icon64\n")
            make_file(source / "app" / "ui" / "images" / "256.png", b"icon256\n")
            make_file(downloads / "bootimus-linux-amd64", b"fake-binary\n")

            package_path = build_fpk.build_package(
                source_dir=source,
                downloads_dir=downloads,
                dist_dir=dist,
                version="0.1.70-1",
                platform="x86",
                asset_name="bootimus-linux-amd64",
            )

            self.assertEqual(package_path.name, "App.Native.Bootimus_0.1.70-1_x86.fpk")
            self.assertEqual(package_path.read_bytes()[:2], b"\x1f\x8b")

            with tarfile.open(package_path, "r:gz") as outer:
                outer_names = set(outer.getnames())
                self.assertTrue(
                    {
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
                    }.issubset(outer_names)
                )
                self.assertEqual(outer.getmember("cmd/main").mode, 0o755)
                privilege = json.loads(outer.extractfile("config/privilege").read().decode("utf-8"))
                self.assertEqual(privilege["defaults"]["run-as"], "root")
                self.assertEqual(privilege["username"], "App.Native.Bootimus")
                resource = json.loads(outer.extractfile("config/resource").read().decode("utf-8"))
                self.assertEqual(resource, expected_resource())
                wizard_install = json.loads(outer.extractfile("wizard/install").read().decode("utf-8"))
                self.assertGreaterEqual(len(wizard_install), 2)
                self.assertEqual(wizard_install[1]["stepTitle"], "网络配置")
                self.assertIn("wizard_bootimus_iso_dir", json.dumps(wizard_install))
                self.assertIn("wizard_bootimus_admin_password", json.dumps(wizard_install))
                self.assertIn("wizard_bootimus_network_mode", json.dumps(wizard_install))
                self.assertIn("wizard_bootimus_network_parent", json.dumps(wizard_install))
                self.assertIn("wizard_bootimus_network_address", json.dumps(wizard_install))
                self.assertIn("wizard_bootimus_network_gateway", json.dumps(wizard_install))
                network_mode_item = next(
                    item for item in wizard_install[1]["items"] if item.get("field") == "wizard_bootimus_network_mode"
                )
                self.assertEqual([option["value"] for option in network_mode_item["options"]], ["host", "macvlan", "ipvlan"])
                wizard_uninstall = json.loads(outer.extractfile("wizard/uninstall").read().decode("utf-8"))
                wizard_uninstall_text = json.dumps(wizard_uninstall)
                self.assertIn("wizard_uninstall_data_action", wizard_uninstall_text)
                self.assertIn("keep_all", wizard_uninstall_text)
                self.assertIn("delete_all", wizard_uninstall_text)

                manifest = outer.extractfile("manifest").read().decode("utf-8")
                self.assertIn("appname               = App.Native.Bootimus", manifest)
                self.assertIn("platform              = x86", manifest)
                self.assertNotIn("install_type=root", manifest)
                self.assertIn("source                = thirdparty", manifest)
                self.assertIn(DEFAULT_CREDENTIALS_TEXT, manifest)
                self.assertIn("maintainer_url        = https://github.com/garybowers/bootimus", manifest)
                self.assertIn("distributor_url       = https://github.com/garybowers/bootimus", manifest)
                self.assertIn("os_min_version        = 0.9.0", manifest)
                self.assertIn("ctl_stop              = true", manifest)
                self.assertIn("desktop_uidir         = ui", manifest)
                self.assertIn("desktop_applaunchname = App.Native.Bootimus.Web", manifest)
                self.assertIn("checkport             = false", manifest)
                self.assertIn("changelog             = Bootimus v0.1.70 个人自用飞牛包。", manifest)
                self.assertNotIn("PXE/HTTP boot server.", manifest)
                self.assertNotIn("personal fnOS package metadata alignment", manifest)
                self.assertRegex(manifest, r"checksum              = [0-9a-f]{32}")

                app_bytes = outer.extractfile("app.tgz").read()

            with tarfile.open(fileobj=io.BytesIO(app_bytes), mode="r:gz") as app_tar:
                app_names = set(app_tar.getnames())
                self.assertTrue(
                    {
                        "bootimus",
                        "bootimus.example.yaml",
                        "ui",
                        "ui/config",
                        "ui/images",
                        "ui/images/64.png",
                        "ui/images/256.png",
                        "config",
                        "config/privilege",
                        "config/resource",
                    }.issubset(app_names)
                )
                self.assertNotIn("app/bootimus", app_names)
                self.assertEqual(app_tar.getmember("bootimus").mode, 0o755)
                ui_config = app_tar.extractfile("ui/config").read().decode("utf-8")
                self.assertIn("App.Native.Bootimus.Web", ui_config)
                self.assertIn('"port": "8081"', ui_config)

    def test_source_declares_visible_app_files_and_custom_iso_dir(self):
        resource = json.loads((ROOT / "fnos-appstore-bootimus" / "config" / "resource").read_text(encoding="utf-8"))
        self.assertEqual(resource, expected_resource())

        wizard_install = (ROOT / "fnos-appstore-bootimus" / "wizard" / "install").read_text(encoding="utf-8")
        wizard_install_data = json.loads(wizard_install)
        self.assertGreaterEqual(len(wizard_install_data), 2)
        self.assertEqual(wizard_install_data[0]["stepTitle"], "Bootimus 配置")
        self.assertEqual(wizard_install_data[1]["stepTitle"], "网络配置")
        self.assertNotIn("wizard_bootimus_network_mode", json.dumps(wizard_install_data[0], ensure_ascii=False))
        self.assertIn("wizard_bootimus_network_mode", json.dumps(wizard_install_data[1], ensure_ascii=False))
        network_mode_item = next(
            item for item in wizard_install_data[1]["items"] if item.get("field") == "wizard_bootimus_network_mode"
        )
        self.assertEqual([option["value"] for option in network_mode_item["options"]], ["host", "macvlan", "ipvlan"])
        self.assertIn("wizard_bootimus_iso_dir", wizard_install)
        self.assertIn("wizard_bootimus_admin_password", wizard_install)
        self.assertIn("wizard_bootimus_network_mode", wizard_install)
        self.assertIn("wizard_bootimus_network_parent", wizard_install)
        self.assertIn("wizard_bootimus_network_address", wizard_install)
        self.assertIn("wizard_bootimus_network_gateway", wizard_install)
        self.assertIn("独立 IP", wizard_install)
        self.assertIn("ISO", wizard_install)
        self.assertIn("应用文件", wizard_install)
        self.assertIn(DEFAULT_CREDENTIALS_TEXT, wizard_install)

        install_callback = (ROOT / "fnos-appstore-bootimus" / "cmd" / "install_callback").read_text(encoding="utf-8")
        self.assertIn("wizard_bootimus_iso_dir", install_callback)
        self.assertIn("wizard_bootimus_admin_password", install_callback)
        self.assertIn("wizard_bootimus_network_mode", install_callback)
        self.assertIn("wizard_bootimus_network_parent", install_callback)
        self.assertIn("wizard_bootimus_network_address", install_callback)
        self.assertIn("wizard_bootimus_network_gateway", install_callback)
        self.assertIn("BOOTIMUS_ISO_DIR", install_callback)
        self.assertIn("BOOTIMUS_ADMIN_PASSWORD", install_callback)
        self.assertIn("BOOTIMUS_NETWORK_MODE", install_callback)
        self.assertIn("BOOTIMUS_NETWORK_PARENT", install_callback)
        self.assertIn("BOOTIMUS_NETWORK_ADDRESS", install_callback)
        self.assertIn("BOOTIMUS_NETWORK_GATEWAY", install_callback)
        self.assertIn("BOOTIMUS_NETWORK_DHCP", install_callback)
        self.assertIn("wizard raw network values", install_callback)
        self.assertIn('wizard_network_mode="macvlan"', install_callback)
        self.assertNotIn("BOOTIMUS_DATA_DIR=", install_callback)

        main = (ROOT / "fnos-appstore-bootimus" / "cmd" / "main").read_text(encoding="utf-8")
        self.assertIn('DATA_ROOT="${APP_SHARE}"', main)
        self.assertIn('DEFAULT_BOOTIMUS_DATA_DIR="${DATA_ROOT}/data"', main)
        self.assertIn('--data-dir "${BOOTIMUS_DATA_DIR}"', main)
        self.assertIn("WIZARD_ISO_DIR_FILE", main)
        self.assertIn('BOOTIMUS_INTERNAL_ISO_DIR="${BOOTIMUS_DATA_DIR}/isos"', main)
        self.assertIn("BOOTIMUS_ISO_DIR", main)
        self.assertIn("mount --bind", main)
        self.assertIn("sync_external_iso_files", main)
        self.assertIn("mount_external_iso_files", main)
        self.assertIn("unmount_external_iso_files", main)
        self.assertIn("external_iso_mount_target_from_marker", main)
        self.assertIn("External ISO directory is read-only", main)
        self.assertNotIn('mount --bind "${BOOTIMUS_ISO_DIR}" "${BOOTIMUS_INTERNAL_ISO_DIR}"', main)
        self.assertIn("BOOTIMUS_ADMIN_PASSWORD", main)
        self.assertIn("/api/login", main)
        self.assertIn("/api/users/reset-password", main)
        self.assertIn("BOOTIMUS_NETWORK_MODE", main)
        self.assertIn("BOOTIMUS_NETNS", main)
        self.assertIn("ip netns add", main)
        self.assertIn("type ipvlan mode l2", main)
        self.assertIn("type macvlan mode bridge", main)
        self.assertIn("ip netns exec", main)
        self.assertIn("BOOTIMUS_LAUNCH_PROXY_PID_FILE", main)
        self.assertIn("BOOTIMUS_NETWORK_WATCHER_PID_FILE", main)
        self.assertIn("start_launch_redirect", main)
        self.assertIn("start_python_launch_redirect", main)
        self.assertIn("do_HEAD", main)
        self.assertIn("wait_for_launch_redirect_pid", main)
        self.assertLess(main.index("start_python_launch_redirect"), main.index("busybox httpd"))
        self.assertIn("start_network_watcher", main)
        self.assertIn("stop_network_watcher", main)
        self.assertIn("network watcher detected IP change", main)
        self.assertIn("network watcher restarting Bootimus", main)
        self.assertIn("bootimus_service_ip", main)
        self.assertIn("BOOTIMUS_NETWORK_DHCP", main)
        self.assertIn("run_network_dhcp", main)
        self.assertIn("udhcpc", main)
        self.assertIn("dhclient", main)
        self.assertIn("detect_default_parent_interface", main)
        self.assertIn("ip route get", main)
        self.assertIn("lifecycle_log", main)
        self.assertIn("run_with_timeout", main)
        self.assertIn("start_app entered", main)
        self.assertIn("prepare_network_namespace", main)
        self.assertIn("DHCP uses macvlan", main)
        self.assertIn("python timeout fallback", main)
        self.assertNotIn("falling back to host network", main)

    def test_user_facing_package_text_is_chinese(self):
        build_fpk = load_build_module()

        app_tgz = b"fake-app"
        manifest = build_fpk.render_manifest("0.1.70-test", "x86", app_tgz)
        self.assertIn("PXE/HTTP 启动维护服务", manifest)
        self.assertIn("个人自用飞牛包", manifest)
        self.assertNotIn("PXE/HTTP boot server", manifest)
        self.assertNotIn("personal fnOS package", manifest)

        ui_config = json.loads(build_fpk.render_ui_config())
        entry = ui_config[".url"]["App.Native.Bootimus.Web"]
        self.assertIn("管理界面", entry["desc"])
        self.assertNotIn("admin console", entry["desc"])

        notices = (ROOT / "fnos-appstore-bootimus" / "app" / "THIRD_PARTY_NOTICES.md").read_text(encoding="utf-8")
        self.assertIn("第三方声明", notices)
        self.assertIn("个人自用飞牛包", notices)
        self.assertNotIn("This personal fnOS package", notices)
        self.assertNotIn("GitHub Release", notices)

        license_text = (ROOT / "fnos-appstore-bootimus" / "LICENSE").read_text(encoding="utf-8")
        self.assertIn("个人自用", license_text)
        self.assertIn("开源许可证", license_text)
        self.assertNotIn("provided for personal use", license_text)
        self.assertNotIn("redistributed under", license_text)
        self.assertNotIn("Apache License", license_text)

    def test_source_declares_uninstall_data_policy(self):
        wizard_uninstall = (ROOT / "fnos-appstore-bootimus" / "wizard" / "uninstall").read_text(encoding="utf-8")
        self.assertIn("wizard_uninstall_data_action", wizard_uninstall)
        self.assertIn("keep_all", wizard_uninstall)
        self.assertIn("delete_all", wizard_uninstall)
        self.assertIn("保留用户数据", wizard_uninstall)
        self.assertIn("清除全部数据", wizard_uninstall)
        self.assertIn("保留 ISO 目录", wizard_uninstall)

        uninstall_callback = (ROOT / "fnos-appstore-bootimus" / "cmd" / "uninstall_callback").read_text(encoding="utf-8")
        for marker in [
            "wizard_uninstall_data_action",
            "keep_all",
            "delete_all",
            "safe_delete_tree()",
            "unmount_external_iso_files",
            "uninstall requested; keeping user data",
            "uninstall requested; deleting all app data",
            "preserving bootimus ISO/data directory",
        ]:
            self.assertIn(marker, uninstall_callback)
        self.assertNotIn("load_saved_bootimus_data_dir()", uninstall_callback)
        self.assertNotIn("BOOTIMUS_DATA_DIR", uninstall_callback)

    def test_source_normalizes_windows_wimboot_params_for_uefi(self):
        main = (ROOT / "fnos-appstore-bootimus" / "cmd" / "main").read_text(encoding="utf-8")

        self.assertIn("normalize_windows_wimboot_params", main)
        self.assertIn("wimboot rawbcd compatibility", main)
        self.assertIn("sqlite3.connect(db_path)", main)
        self.assertIn("UPDATE distro_profiles", main)
        self.assertIn("UPDATE images", main)
        self.assertIn("REPLACE", main)
        self.assertIn("rawbcd", main)
        self.assertIn("Windows wimboot boot_params normalized", main)
        self.assertIn("start_app normalized Windows wimboot params", main)

        start_app = main[main.index("start_app() {"):main.index("stop_app() {")]
        self.assertIn("normalize_windows_wimboot_params", start_app)
        self.assertLess(start_app.index("normalize_windows_wimboot_params"), start_app.index("apply_admin_password"))


if __name__ == "__main__":
    unittest.main()
