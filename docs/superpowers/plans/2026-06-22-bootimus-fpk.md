# Bootimus FPK Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Build personal-use fnOS `.fpk` packages for Bootimus v0.1.70 on x86 and ARM.

**Architecture:** Package the official static Bootimus Linux binaries inside a native fnOS app layout. The app runs as root so Bootimus can bind PXE/TFTP ports, stores durable data under the fnOS data-share path, and exposes the admin UI through a desktop iframe entry on port 8081.

**Tech Stack:** Python `tarfile` packer, shell lifecycle scripts, fnOS native app manifest/config files, official Bootimus release binaries.

---

### Task 1: Package Source Layout

**Files:**
- Create: `fnos-appstore-bootimus/cmd/main`
- Create: `fnos-appstore-bootimus/config/privilege`
- Create: `fnos-appstore-bootimus/config/resource`
- Create: `fnos-appstore-bootimus/app/bootimus.example.yaml`
- Create: `fnos-appstore-bootimus/app/ui/config`

- [ ] Create a root-running lifecycle script that copies the installed binary into `${TRIM_PKGVAR}/bin`, writes logs under the data-share directory, starts `bootimus serve`, stops by PID, reports status, and writes `${TRIM_TEMP_LOGFILE}` on startup failures.
- [ ] Configure `run-as: root` and `install_type=root`.
- [ ] Add a desktop entry pointing at `http://<host>:8081/`.

### Task 2: Build Script

**Files:**
- Create: `scripts/build-fpk.py`
- Create: `tests/test_build_fpk.py`

- [ ] Write tests that build a tiny fake package and assert gzip `.fpk`, required outer files, `app.tgz` top-level layout, executable modes for `cmd/main` and `bootimus`, and matching desktop entry metadata.
- [ ] Implement the Python builder with explicit tar modes so Windows does not drop Linux execute bits.
- [ ] Download/copy official `bootimus-linux-amd64` and `bootimus-linux-arm64` assets into `.tmp/downloads`.
- [ ] Generate `dist/bootimus_0.1.70-1_x86.fpk` and `dist/bootimus_0.1.70-1_arm.fpk`.

### Task 3: Verification

**Files:**
- Inspect generated files under `dist/`

- [ ] Run the unit tests.
- [ ] Build both packages.
- [ ] Inspect gzip magic, outer members, inner `app.tgz` layout, manifest platform, and executable modes.
- [ ] Record SHA256 checksums.
