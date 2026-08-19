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
| Windows x64 | `DiskForge-v0.7.0-windows-x64.zip` | 解压后运行 `DiskForge.exe`。 |
| Linux x64 | `DiskForge-v0.7.0-linux-x64.zip` | 解压后运行 `./DiskForge`。 |
| macOS Intel | `DiskForge-v0.7.0-macos-intel-x64.zip` | 解压后将 `DiskForge.app` 移至“应用程序”。 |
| macOS Apple Silicon | `DiskForge-v0.7.0-macos-arm64.zip` | 解压后将 `DiskForge.app` 移至“应用程序”。 |

## v0.7.0 集中收敛能力

v0.7.0 在既有启动、部署、虚拟磁盘与自动化工作流基础上，集中修复历史软盘兼容、内置文件预览、界面本地化、应用图标与离屏验证日志。旧式无 FAT 显示标签的 FAT12/16/32 映像会由 BPB、几何、介质描述符与启动签名交叉验证后直接打开；`.IMA` 作为原始映像别名处理。双击文件不再依赖系统默认打开方式：文本、图像、常见压缩包、传统安装包、可执行文件与二进制数据均会先在隔离临时目录中以只读方式在 DiskForge 内检查，绝不执行内容。现在可从目录及可选本地启动映像创建带 El Torito 目录的 ISO；外部启动映像只会复制进入新 ISO，源文件保持不变。启动扇区提供完全原创的中性停机和 DiskForge 消息模板，保留 FAT BPB 并在写入前创建完整映像备份。固定 VHD 通过临时 RAW 数据视图只读浏览，关闭后自动清理；配置转换器后其他虚拟格式同样可获得临时只读浏览路径。FAT 部署先生成可审阅的中性 MBR 单分区映像，随后仍须进入独立、受 `ERASE` 保护的物理写入工作流。批处理新增无副作用预演与 CLI `--dry-run`，桌面会在执行前展示计划；任务中心显示排队、运行、完成、失败和取消状态。显式可移植模式使用 INI 保存语言、主题、字体、最近映像和外部工具设置，项目继续采用“警告即错误”的 pytest 严格门槛。

## 核心能力

DiskForge 将专业映像管理流程整合到统一界面。主窗口包含映像资源树、目录表格、映像信息面板、活动日志以及可取消进度区；破坏性操作会与常规浏览操作分开呈现。

| 工作流 | 原生能力 | 说明 |
|---|---|---|
| 创建映像 | RAW/IMG、FAT12、FAT16、FAT32、DMF 布局 FAT12、ISO9660/Joliet | 创建可编辑 FAT 映像、采用 80×2×21 扇区已知几何布局的 DMF 映像、普通 ISO，或从本地目录和可选启动映像制作 El Torito ISO。 |
| 浏览与提取 | FAT12/16/32（包含经过验证的无显示标签旧式 DOS 软盘）、ISO9660/Joliet、固定 VHD 数据视图 | 目录树、可排序详细表格、持久化图标网格，以及无需系统默认程序的只读双击预览。文本、图像、常见压缩包、传统安装包、可执行文件和二进制数据均可安全检查；固定 VHD 以排除尾部元数据的临时 RAW 只读视图打开。 |
| 修改映像内容 | FAT 文件/目录注入、删除、时间属性编辑 | 可将本地文件或目录直接拖入可编辑 FAT 映像，也可投放到当前显示的目标目录；ISO 按只读介质处理。 |
| 格式转换 | 原生 RAW/IMG 与固定 VHD | VHDX、VMDK、QCOW2 通过显式配置的 `qemu-img` 适配器处理。 |
| FAT 紧凑整理 | 基于重建的碎片整理 | 输出新映像，原映像保留作为恢复点。 |
| 结构与启动检查 | 512 字节十六进制查看/编辑、FAT BPB 属性、原创启动模板、中性 MBR FAT 封装与部署规划、尾部零扇区裁剪、El Torito 引导目录 | 模板保留 BPB 且不使用导入的启动程序；结构修改先备份，封装、部署预处理和裁剪均输出新文件。 |
| 校验与自动化 | SHA-256、图形设计器、预演计划、JSON 批处理、可审计日志 | 图形设计器会预览安全的递增名称；`--dry-run` 可在不改动任何文件或设备前审阅操作，无人值守批处理会明确拒绝物理设备写入。 |
| 再分发归档 | 经身份验证的 `.dfb` 容器和带 SHA-256 校验的多映像自解压 `.pyz` 归档 | `.dfb` 支持可选 AES-256-GCM 加密、压缩、注释及逐项校验。 |
| 读写物理介质 | 流式读取与恢复 | 拒绝系统盘、已挂载目标和容量不匹配设备；必须输入确认短语。检测到的光学介质为只读，并默认导出为 ISO。 |

## 安全设计

> 磁盘映像工具应当让高风险操作**无法被轻易误触发**。

DiskForge 不会自动挂载映像，也不会自动向物理设备写入数据。FAT 部署会先生成可审阅的中性 MBR 映像，不会绕过物理写入保护。执行物理写入前，程序会检查容量、挂载状态和系统盘标记，并要求准确输入 `ERASE`。写入后可以进行字节校验。启动扇区修改也会先创建完整映像备份。对重要介质操作前，请务必先用可丢弃的测试映像熟悉流程。

## 可移植配置

以 `diskforge --portable` 启动时，语言、主题、字体、最近映像、目录视图及外部工具路径会写入当前目录的 `DiskForgeData/diskforge.ini`。也可使用 `--portable=目录`、`--portable-directory 目录` 或环境变量 `DISKFORGE_PORTABLE_DIR` 指定位置；该模式使用普通 INI 文件，不依赖系统注册表。

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
diskforge-cli create-iso folder bootable.iso --boot-image boot.img --boot-media noemul
diskforge-cli boot-templates
diskforge-cli prepare-fat-deployment demo.img demo-deploy.img
diskforge-cli batch recipe.json --dry-run
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
| 固定 VHD | 支持 | 临时只读数据视图与转换 | 支持 |
| VHDX / VMDK / QCOW2 | 配置适配器后支持 | 通过转换工作流 | 配置适配器后支持 |
| NTFS / EXT / DMG | 签名或分区提示 | 不提供原生修改 | 建议使用兼容的外部工作流 |

DiskForge 会明确暴露不支持的编辑路径，不会进行未经验证的危险写入。若需要虚拟磁盘转换，请在 **Tools → Preferences** 中配置 `qemu-img`；应用不会静默下载或运行外部转换器。

## 工程质量

项目自动化覆盖 FAT 创建与修改、可启动 ISO 和 El Torito 检查、原创启动模板的 BPB 保留与备份、固定 VHD 临时浏览与清理、FAT 部署规划、尾部零扇区报告、原生拖放契约、图形批处理设计与无副作用预演、公共 API 会话、可移植设置、任务中心、字体与目录视图持久化、主题切换、光学介质识别、校验和、MBR 解析、自解压归档、物理写入保护、目录导出和 FAT 重建式整理。pytest 启用严格配置、严格标记和警告即错误；GUI 同时接受离屏启动验证。持续集成会在 Windows、Linux、macOS Intel 和 macOS Apple Silicon 上运行同一质量门槛，并打包每个原生目标。

```bash
QT_QPA_PLATFORM=offscreen pytest
QT_QPA_PLATFORM=offscreen python scripts/gui_smoke.py
```

详细构建与发布说明参阅 [BUILDING.md](docs/BUILDING.md)。界面冒烟验证记录参阅 [gui_validation.md](artifacts/gui_validation.md)。

## 参与贡献

欢迎提交 Issue 和 Pull Request。请保持变更聚焦，为行为变化增加回归测试，且不要提交真实磁盘映像、凭据、私有路径或生成的构建产物。

## 许可证

DiskForge 采用 [MIT License](LICENSE) 发布。
