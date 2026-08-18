<p align="center">
  <img src="assets/diskforge-workspace.png" alt="DiskForge 打开 FAT 映像后的工作区" width="900">
</p>

<h1 align="center">DiskForge</h1>

<p align="center"><strong>面向创建、浏览、转换与安全恢复的跨平台磁盘映像桌面工作台。</strong></p>

<p align="center">
  <a href="https://github.com/Piechicken/diskforge/actions/workflows/ci.yml"><img src="https://github.com/Piechicken/diskforge/actions/workflows/ci.yml/badge.svg?branch=main" alt="构建状态"></a>
  <a href="https://github.com/Piechicken/diskforge/releases"><img src="https://img.shields.io/github/v/release/Piechicken/diskforge?display_name=tag&color=7C3AED" alt="最新版本"></a>
  <a href="LICENSE"><img src="https://img.shields.io/badge/license-MIT-0EA5E9.svg" alt="MIT 许可证"></a>
  <img src="https://img.shields.io/badge/Python-3.10%2B-2563EB.svg" alt="Python 3.10 或更新版本">
  <img src="https://img.shields.io/badge/GUI-Qt-16A34A.svg" alt="Qt 图形界面">
</p>

<p align="center">
  <a href="README.md">English</a> ·
  <a href="README.zh-CN.md">简体中文</a> ·
  <a href="README.ja.md">日本語</a> ·
  <a href="README.es.md">Español</a>
</p>

> **DiskForge 为磁盘映像提供真正的桌面工作区。** 在一个原创、可审计的应用中创建、检查、浏览、提取、注入、转换、校验并安全恢复映像。

## 版本下载

首个公开版本提供四个原生桌面包。请在 [Releases 页面](https://github.com/Piechicken/diskforge/releases) 下载与你的系统相匹配的包：**Windows x64**、**Linux x64**、**macOS Intel** 或 **macOS Apple Silicon**。每个包均由 GitHub Actions 在对应目标运行器上构建和验证。

| 平台 | 文件名 | 启动方式 |
|---|---|---|
| Windows x64 | `DiskForge-v0.1.0-windows-x64.zip` | 解压后运行 `DiskForge.exe`。 |
| Linux x64 | `DiskForge-v0.1.0-linux-x64.zip` | 解压后运行 `./DiskForge`。 |
| macOS Intel | `DiskForge-v0.1.0-macos-intel-x64.zip` | 解压后将 `DiskForge.app` 移至“应用程序”。 |
| macOS Apple Silicon | `DiskForge-v0.1.0-macos-arm64.zip` | 解压后将 `DiskForge.app` 移至“应用程序”。 |

## 核心能力

DiskForge 将专业映像管理流程整合到统一界面。主窗口包含映像资源树、目录表格、映像信息面板、活动日志以及可取消进度区；破坏性操作会与常规浏览操作分开呈现。

| 工作流 | 原生能力 | 说明 |
|---|---|---|
| 创建映像 | RAW/IMG、FAT12、FAT16、FAT32、ISO9660/Joliet | 创建可编辑 FAT 映像，或从本地目录制作 ISO。 |
| 浏览与提取 | FAT12/16/32、ISO9660/Joliet | 目录树、批量提取、映像信息和 MBR/GPT 检查。 |
| 修改映像内容 | FAT 文件/目录注入、删除、时间属性编辑 | ISO 按只读介质处理，可由本地目录重新构建。 |
| 格式转换 | 原生 RAW/IMG 与固定 VHD | VHDX、VMDK、QCOW2 通过显式配置的 `qemu-img` 适配器处理。 |
| FAT 紧凑整理 | 基于重建的碎片整理 | 输出新映像，原映像保留作为恢复点。 |
| 启动扇区检查 | 512 字节十六进制查看/编辑、导入扇区 | 替换前自动创建完整映像备份。 |
| 校验与自动化 | SHA-256、JSON 批处理、可审计日志 | 无人值守批处理会明确拒绝物理设备写入。 |
| 再分发归档 | 带 SHA-256 校验的自解压 `.pyz` 归档 | 可纳入原生启动器打包流程。 |
| 读写物理介质 | 流式读取与恢复 | 拒绝系统盘、已挂载目标和容量不匹配设备；必须输入确认短语。 |

## 安全设计

> 磁盘映像工具应当让高风险操作**无法被轻易误触发**。

DiskForge 不会自动挂载映像，也不会自动向物理设备写入数据。执行物理写入前，程序会检查容量、挂载状态和系统盘标记，并要求准确输入 `ERASE`。写入后可以进行字节校验。启动扇区修改也会先创建完整映像备份。对重要介质操作前，请务必先用可丢弃的测试映像熟悉流程。

## 快速开始

### 从源码运行

```bash
python -m pip install -e '.[dev]'
diskforge
```

### 使用命令行

```bash
diskforge-cli create-fat demo.img --size-mib 32 --fat 16
diskforge-cli info demo.img
diskforge-cli list demo.img
diskforge-cli --help
```

### 构建原生应用包

```bash
python scripts/build.py
```

请在对应目标操作系统上构建其原生应用包。仓库工作流会自动完成四个发布目标的构建。

## 格式支持范围

| 格式或文件系统 | 检查 | 浏览/修改 | 创建/转换 |
|---|---:|---:|---:|
| RAW / IMG / IMA / BIN | 支持 | FAT 载荷 | 支持 |
| FAT12 / FAT16 / FAT32 | 支持 | 支持 | 支持 |
| ISO9660 / Joliet | 支持 | 只读浏览与提取 | 从目录创建 |
| 固定 VHD | 支持 | 转换载荷 | 支持 |
| VHDX / VMDK / QCOW2 | 配置适配器后支持 | 通过转换工作流 | 配置适配器后支持 |
| NTFS / EXT / DMG | 签名或分区提示 | 不提供原生修改 | 建议使用兼容的外部工作流 |

DiskForge 会明确暴露不支持的编辑路径，不会进行未经验证的危险写入。若需要虚拟磁盘转换，请在 **Tools → Preferences** 中配置 `qemu-img`；应用不会静默下载或运行外部转换器。

## 工程质量

项目自动化覆盖 FAT 创建与修改、ISO 创建/提取、固定 VHD、校验和、MBR 解析、自解压归档、物理写入保护、启动扇区备份、目录导出和 FAT 重建式整理。GUI 同时接受离屏启动验证。持续集成会在 Windows、Linux、macOS Intel 和 macOS Apple Silicon 上运行测试，并打包每个原生目标。

```bash
QT_QPA_PLATFORM=offscreen pytest
QT_QPA_PLATFORM=offscreen python scripts/gui_smoke.py
```

详细构建与发布说明参阅 [BUILDING.md](docs/BUILDING.md)。界面冒烟验证记录参阅 [gui_validation.md](artifacts/gui_validation.md)。

## 参与贡献

欢迎提交 Issue 和 Pull Request。请保持变更聚焦，为行为变化增加回归测试，且不要提交真实磁盘映像、凭据、私有路径或生成的构建产物。

## 许可证

DiskForge 采用 [MIT License](LICENSE) 发布。
