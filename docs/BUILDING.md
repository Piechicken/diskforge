# 构建与发布指南

DiskForge 使用 Python、PySide6 和 PyInstaller。由于桌面可执行文件包含平台相关运行时，应该在目标操作系统上构建对应产物，而不是从 Linux 交叉构建 Windows 或 macOS 版本。

| 目标平台 | 开发启动方式 | 打包结果 | 物理盘权限提示 |
|---|---|---|---|
| Windows 10/11 | `diskforge` | `dist/DiskForge/DiskForge.exe` | 读取或写入 `\\.\PhysicalDriveN` 通常需要管理员终端。 |
| macOS | `diskforge` | `dist/DiskForge.app` | `diskutil` 列表可用；写入 `/dev/diskN` 前须解除挂载，并按系统权限要求运行。 |
| Linux | `diskforge` | `dist/DiskForge/DiskForge` | 需要能访问目标 `/dev/*` 的权限；不要对已挂载设备写入。 |

## 环境配置

应使用 Python 3.10 或更高版本。建议新建虚拟环境，再安装项目的开发依赖：

```bash
python -m venv .venv
# Windows: .venv\Scripts\activate
# macOS/Linux: source .venv/bin/activate
python -m pip install --upgrade pip
python -m pip install -e '.[dev]'
```

可选的 `qemu-img` 扩展 VHDX、VMDK 与 QCOW2 的检查/转换。请由系统包管理器或 QEMU 官方发行版安装它，并在 **Tools → Preferences** 指定其可执行文件路径。应用不会自动下载、安装或在未经用户选择时调用外部转换器。

## 本机构建

```bash
python scripts/build.py
```

构建脚本会收集 Qt、FAT、ISO 与文件系统依赖，并生成当前操作系统原生包。为减少供应链风险，应在干净的构建机上执行发布构建，并对发布的压缩包与源代码标签分别计算 SHA-256。

## GitHub Actions

仓库的 [`.github/workflows/ci.yml`](../.github/workflows/ci.yml) 在 Ubuntu、Windows 与 macOS 上执行测试，并在每个平台生成独立构建工件。Linux 任务还运行离屏 GUI 冒烟测试并上传截图。CI 产物旨在供测试；正式发布前仍应在真实平台启动 GUI、打开 FAT/ISO 测试映像、检查原始设备权限和签名策略。

## Windows 自解压包

DiskForge 原生生成可验证的 `.pyz` 自解压归档。若需要 Windows `.exe` 启动体验，可使用同一 PyInstaller 流程构建一个最小 Python 启动器来运行该归档；归档本身含有映像 SHA-256 清单，并会在提取完成后核验。该设计避免把不可审计的专用提取器写入映像。
