# Bootimus fnOS FPK

Bootimus 的个人自用飞牛 fnOS FPK 打包工程。

## 功能

- 打包 Bootimus `v0.1.70` 的 x86 和 arm FPK。
- 安装引导支持自定义 ISO 镜像目录。
- 应用数据、日志和运行文件默认放在飞牛应用文件目录，ISO 目录只用于放镜像。
- 支持宿主机网络、macvlan 独立 IP、ipvlan 静态地址模式。
- 独立 IP 留空时走 DHCP，并优先使用 macvlan。
- 卸载时支持保留用户数据或清除应用数据，外部 ISO 目录不会被删除。

## 构建

```powershell
python scripts\build-fpk.py --version 0.1.70-19 --platform all
```

如果 `.tmp/downloads` 已经有 Bootimus 二进制，可跳过下载：

```powershell
python scripts\build-fpk.py --version 0.1.70-19 --platform all --skip-download
```

构建产物输出到 `dist/`，该目录不会提交到 git。

## 测试

```powershell
python tests\test_build_fpk.py
python -m py_compile scripts\build-fpk.py
```

在 Windows 上也可以用 Git Bash 检查生命周期脚本语法：

```powershell
& 'C:\Program Files\Git\bin\bash.exe' -n fnos-appstore-bootimus/cmd/main fnos-appstore-bootimus/cmd/install_callback fnos-appstore-bootimus/cmd/uninstall_callback
```

## 默认登录

默认账号是 `admin`。如果安装引导里没有填写初始密码，Bootimus 首次启动会随机生成密码，请到应用文件目录里的 `bootimus/logs/bootimus.log` 查看。

## 上游

Bootimus 上游项目：[garybowers/bootimus](https://github.com/garybowers/bootimus)
