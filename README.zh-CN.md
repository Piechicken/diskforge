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
| Windows x64 | `DiskForge-v0.8.0-windows-x64.zip` | 解压后运行 `DiskForge.exe`。 |
| Linux x64 | `DiskForge-v0.8.0-linux-x64.zip` | 解压后运行 `./DiskForge`。 |
| macOS Intel | `DiskForge-v0.8.0-macos-intel-x64.zip` | 解压后将 `DiskForge.app` 移至“应用程序”。 |
| macOS Apple Silicon | `DiskForge-v0.8.0-macos-arm64.zip` | 解压后将 `DiskForge.app` 移至“应用程序”。 |

## v0.8.0 文档式工作区与不可覆盖发布

v0.8.0 在保留可编辑文档式工作区的基础上，新增了从经过验证的 BPB 模板创建 FAT 映像、仅导入启动代码且保留目标 FAT BPB 并先做完整备份的 512 字节启动扇区文件安全导入，以及在验证虚拟数据区和页脚后可作为可写 FAT 会话重新打开的独立固定 VHD 副本。原始 VHD 不会被修改；动态 VHD 不进入原生写入路径。

外部适配器均明确标示：`qemu-img` 是用于 VHDX、VMDK 和 QCOW2 的可选适配器，提供能力报告和可取消进程；可选的 `dmg2img` 只能将 DMG 转换为新的原始 HFS+ 输出，DiskForge 不会挂载或写入 DMG。新的采集队列只读取所选可移动或光学介质、创建独立文件并记录 SHA-256 审计，完全不包含设备写入选项。上述新增路径与既有文档工作区均已覆盖联合国六种工作语言和日语。发布工作流只接受 `v*` 标签，强制校验标签与项目版本相同；若 Release 已存在则直接失败，绝不覆盖任何版本资产。

## v0.10.0.dev0：安全 ISO 重建与 IMG/IMA 老式软盘

当前开发版本将 **IMA** 作为独立的一等原始映像格式，而不是仅作为 IMG 的文件名别名。桌面程序、命令行、图形批处理设计器和批处理执行器均可明确选择 `.ima` 或 `.img` 输出。新建映像提供经过重开验证的 FAT12 老式软盘预设：覆盖常见 PC 兼容 5.25 英寸与 3.5 英寸的 160 KiB 至 2.88 MiB 布局，包括 DMF 和 82 磁道布局；也可在明确输入柱面、磁头、每磁道扇区和受支持扇区大小后创建自定义几何。有效 FAT IMA 与 FAT IMG 具有相同的浏览、内置预览、注入、删除、改名、属性、提取、哈希与转换能力。

ISO 内容编辑采用单独输出的重建方式。它会核验暂存文件哈希并保留 Rock Ridge/UDF profile；经验证的单初始 El Torito 启动条目也能保留。多节/多启动目录、混合系统区或无法唯一映射的启动目录会被明确拒绝，绝不冒险重写。批处理 v4 的 `iso_edit` 使用同一安全核心。

> 对于 128/256 字节扇区、GCR 或变速扇区、硬分区、非 FAT、复制保护轨道及 flux/bitcell 捕获等历史格式，DiskForge 仅承诺原始字节保存、检查、校验与比较；不会将其虚报为可安全文件级编辑的 FAT 映像。

## 核心能力

DiskForge 将专业映像管理流程整合到统一界面。主窗口包含映像资源树、目录表格、映像信息面板、活动日志以及可取消进度区；破坏性操作会与常规浏览操作分开呈现。

| 工作流 | 原生能力 | 说明 |
|---|---|---|
| 创建映像 | RAW/IMG/IMA、FAT12、FAT16、FAT32、经过验证的老式 FAT12 软盘预设、DMF 布局 FAT12、ISO9660/Joliet/Rock Ridge/UDF、可选经典 HFS | 可创建标准可编辑 FAT 映像、明确的 IMG/IMA 老式软盘预设或受支持自定义 CHS 几何、DMF 映像，以及含可选 El Torito 启动介质的 ISO。显式可用 `hformat` 时，DiskForge 可从 800 KiB 起创建新的独立经典 HFS 常规文件映像；HFS+ 始终保持只读。 |
| 浏览与提取 | FAT12/16/32（包含经过验证的无显示标签旧式 DOS 软盘）、保守的 FAT12/FAT16 已删除根目录文件候选、只读 IMD 扇区检查、ISO9660/Joliet、安全单映像 ZIP 容器、固定 VHD 数据视图，以及可选 NTFS/EXT/经典 HFS/HFS+ 只读后端 | 普通 ZIP 仅在恰有一个安全的根级映像载荷时，才会物化到自动清理的私有只读会话；它绝不会变为可写或可转换映像。目录树和表格采用确定性分页与排序缓存，不会无界加载大目录。经验证的 MBR/GPT 分区始终按显式表索引选择：FAT 保留现有编辑路径，NTFS/EXT/经典 HFS/HFS+ 仅按精确验证偏移经只读后端打开。双击会打开无需系统默认程序的文档式工作区：文本可查找、另存副本，且仅在可写 FAT 条目中可编辑后保存回映像；图像、常见压缩包、传统安装包、可执行文件和二进制数据均以安全、不执行的方式检查。固定 VHD 以排除尾部元数据的临时 RAW 只读视图打开。 |
| 修改映像内容 | FAT 文件/目录注入、删除、改名、跨目录移动常规文件、时间属性编辑；安全的 ISO 重建编辑；可选 NTFS/EXT/经典 HFS 受控注入 | FAT IMG 与 IMA 共享完整可编辑工作流。常规文件可移动到已有目录而不覆盖；根目录、缺失或非目录目标、同名冲突、只读会话和所有目录移动均会在修改前被拒绝。同目录改名仍是独立操作。ISO 编辑始终输出新的重建映像并核验暂存内容，保留 Rock Ridge/UDF；仅可保留已验证的单初始 El Torito 条目，多启动、混合或歧义启动布局会被拒绝。若显式提供 `ntfsprogs`、`e2fsprogs` 或 `hfsutils` 后端，NTFS/EXT/经典 HFS 只能将新的根目录常规文件写入独立且已验证的输出映像；不允许原映像、分区偏移、元数据、改名、删除或覆盖写入。经典 HFS 仅传输原始数据 fork；HFS+ 保持只读。 |
| 格式转换 | 原生 RAW/IMG/IMA 与固定 VHD | IMG 与 IMA 转换会保留用户明确选择的原始映像扩展名；VHDX、VMDK、QCOW2 通过显式配置的 `qemu-img` 适配器处理。 |
| FAT 紧凑整理 | 基于重建的碎片整理 | 输出新映像，原映像保留作为恢复点。 |
| 结构与启动检查 | 512 字节十六进制查看/编辑、FAT BPB 属性、原创启动模板、中性 MBR FAT 封装与部署规划、尾部零扇区裁剪、El Torito 引导目录 | 模板保留 BPB 且不使用导入的启动程序；结构修改先备份，封装、部署预处理和裁剪均输出新文件。 |
| 校验与自动化 | SHA-256、图形全操作配方编辑器、预演计划、逐项结果审阅、JSON 批处理、可审计日志与目录报告 | 批处理 v4 支持声明式 `iso_edit`、`ntfs_inject`、`ext_inject`、`hfs_inject`、`hfs_create`、`export_listing` 与 FAT `move`；`export_listing` 仅创建本地文本/HTML 报告，且可指定显式只读分区。所有可浏览文件系统和显式只读分区均可通过同一稳定完整遍历导出文本/HTML 目录报告；图形设计器可新建、重新打开和编辑转换、校验、比较、缩放、注入、经典 HFS 新建、提取和容器操作配方；`--dry-run` 可在不改动任何文件或设备前审阅操作，无人值守批处理会明确拒绝物理设备写入。 |
| 再分发归档 | 经身份验证的 `.dfb` 容器和带 SHA-256 校验的多映像自解压 `.pyz` 归档 | `.dfb` 支持可选 AES-256-GCM 加密、压缩、注释及逐项校验。每个原生平台包还附带独立的 `DiskForgeExtractor`，可在接收端未预装 Python 时验证并解开 `.pyz` 载荷。 |
| 读写物理介质 | 流式读取与恢复 | 拒绝系统盘、已挂载目标和容量不匹配设备；必须输入确认短语。检测到的光学介质为只读，并默认导出为 ISO。 |
| 低级软盘格式化 | Linux 控制器软盘与已探测 UFI USB 软驱后端 | `fdformat` 仅用于标准控制器节点。UFI USB 候选必须由 sysfs 关联到可移动介质、通过 `ufiformat -i` 证明设备身份、从报告的容量中明确选择一种并输入 `FORMAT_FLOPPY`；命令始终使用 `-V` 验证。创建 FAT 文件系统仍是需要再次确认的独立操作；每种软驱型号仍需真实硬件验收。 |

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
diskforge-cli list partitioned.img --partition 2
diskforge-cli export-listing partitioned.img partition-report.html --html --partition 2
diskforge-cli move-fat demo.img /README.TXT /DOCS  # /DOCS 必须已存在；仅常规文件
diskforge-cli list archived-image.zip  # 仅一个安全根级映像载荷；只读
diskforge-cli list-deleted-fat demo.img  # 仅 FAT12/FAT16 固定根目录 8.3 候选
diskforge-cli recover-deleted-fat demo.img 17 recovered.bin  # 新建本地输出；绝不写入 demo.img
diskforge-cli imd-info legacy.imd  # 只读磁道/扇区审计
diskforge-cli convert-imd legacy.imd exported.img  # 仅导出已证明的矩形正常数据布局
diskforge-cli create-legacy-floppy win16-disk --profile pc525_dsdd_360 --format ima
diskforge-cli create-legacy-floppy custom-disk --format img --cylinders 80 --heads 2 --sectors-per-track 9
diskforge-cli create-iso folder bootable.iso --boot-image boot.img --boot-media noemul
diskforge-cli edit-iso bootable.iso revised.iso --add README.TXT --mkdir /DOCS
diskforge-cli inject-ntfs standalone.ntfs revised.ntfs PAYLOAD.TXT
diskforge-cli inject-ext standalone.ext4 revised.ext4 PAYLOAD.TXT
diskforge-cli inject-hfs standalone.hfs revised.hfs PAYLOAD.TXT
diskforge-cli create-hfs created.hfs --size-kib 800 --label DISKFORGE
diskforge-cli ntfs-inject-status
diskforge-cli ext-inject-status
diskforge-cli hfs-inject-status
diskforge-cli hfs-create-status
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
| IMD | 只读磁道/扇区检查 | 不直接编辑文件系统；仅在证明完整矩形 CHS 布局与正常数据后导出新的 RAW 文件。 | 不支持新建 IMD 或原地转换。 |
| FAT12 / FAT16 / FAT32 | 支持 | FAT 保持可编辑。FAT12/FAT16 还可列出保守的固定根目录已删除 8.3 候选；恢复仅将一个当前空闲的单簇复制到新的本地文件。 | 支持 |
| ISO9660 / Joliet | 支持 | 只读浏览与提取 | 从目录创建 |
| 固定 VHD | 支持 | 临时只读数据视图与转换 | 支持 |
| VHDX / VMDK / QCOW2 | 配置适配器后支持 | 通过转换工作流 | 配置适配器后支持 |
| NTFS / EXT2 / EXT3 / EXT4 | 签名或分区提示 | 可选 Sleuth Kit 可在 offset-0 或显式选择的经验证 MBR/GPT 分区读取/列举/提取；支持文本/HTML 目录报告。配置 `ntfsprogs` / `e2fsprogs` 后，受控注入仍仅限独立 offset-0 新输出 | 浏览始终只读。注入仅外部后端：独立 offset-0 卷、新根目录常规文件、拒绝覆盖；必须核验源 SHA-256、读回 SHA-256 和文件系统。 |
| HFS / HFS+ | 签名或分区提示 | 可选 Sleuth Kit 可在 offset-0 或显式选择的经验证 MBR/GPT 分区读取/列举/数据 fork 提取；支持文本/HTML 目录报告。经典 HFS 可通过配置的 `hfsutils` 受控注入到新输出，并创建经验证的新常规文件映像 | 分区浏览始终只读。经典 HFS 新建仅允许新常规文件、至少 800 KiB 且按 512 字节对齐、安全的 1–27 字符 ASCII 卷标；拒绝设备、分区映射、已有输出和 `-f`，并在原子提升前核验 HFS 签名与 SHA-256。注入仍限独立 offset-0 卷、新安全根目录常规文件、仅原始数据 fork、拒绝覆盖，必须核验源和每个读回载荷的 SHA-256。HFS+ 保持只读；不支持有日志 HFS+ 写入、资源 fork 重建或文件系统修复。 |
| ZIP 单映像容器（`.zip`） | ZIP 结构与一个候选载荷 | 自动清理的临时物化后，仅可读取/列举/提取/导出报告 | 不支持创建、转换、文件系统编辑或归档写入。必须恰有一个根级、未加密、Stored/Deflated 的 `.img`、`.ima`、`.bin`、`.dd`、`.dmf`、`.iso` 或 `.hfs` 载荷，且不超过 2 GiB 并能重新识别为可浏览映像。 |
| DMG | 签名提示 | 不原生修改 | 建议使用兼容的外部工作流。 |

DiskForge 会明确暴露不支持的编辑路径，不会进行未经验证的危险写入。IMD 会作为软盘扇区容器进行检查，不会自动当作原始或可写文件系统。仅当完整矩形 CHS、固定扇区数量/大小、连续 `1..N` 标识、无可选映射且所有扇区均为正常（包括正常压缩填充）数据时，才可导出新的 RAW 文件。非规则几何、缺失/删除/坏扇区、可变布局、重复记录、映射、尾随字节、设备目标、覆盖、IMD 写入及任何位流/磁通声明都会被拒绝。FAT 已删除文件恢复是受限的**候选复制**流程，而不是通用取证恢复：仅接受 FAT12/FAT16 固定根目录中的普通 8.3 槽位、正长度且不超过一个簇、并且起始簇当前空闲的候选。删除文件名的首字符不可获得，候选字节可能已经陈旧或被覆盖，因此不对原始名称或完整性作任何保证。FAT32、子目录、长文件名、零长度或多簇链、已占用簇、源映像写入、已有输出覆盖、设备恢复与批处理恢复均会被拒绝。普通 ZIP 是受限的**只读单映像容器**，不是通用文件系统或转换源：必须恰有一个安全根级、未加密、Stored/Deflated 且使用认可直接映像扩展名、不超过 2 GiB 的载荷。多条目、文件夹、不安全名称、加密、未知压缩、空/过大/未知载荷、递归容器、虚拟磁盘链、转换以及所有 ZIP 写入均会拒绝；临时字节在正常关闭、错误和取消时都会删除。FAT 文件移动明确限制为一个常规文件移动到一个已有目标目录：绝不覆盖或合并条目，并且由于可用的通用目录实现采用“复制后删除”、不具备原子性，目录移动会被拒绝。若需要虚拟磁盘转换，请在 **Tools → Preferences** 中配置 `qemu-img`；NTFS/EXT/HFS/HFS+ 只读浏览需要本地 Sleuth Kit 的 `fls` 与 `icat`，可选受控注入需要显式配置 `ntfscp`/`ntfsls`/`ntfscat`、`debugfs`/`e2fsck`，或仅对经典 HFS 配置用于注入的 `hmount`/`hcopy`/`hls` 或用于已验证新建的 `hformat`。应用不会静默下载、挂载或运行外部工具。详见 [FILESYSTEM_INJECTION.md](docs/FILESYSTEM_INJECTION.md)。

## 工程质量

项目自动化覆盖 FAT 创建、安全常规文件移动、安全 ZIP 单映像物化与清理、保守 FAT 已删除候选恢复、只读 IMD 检查和严格 RAW 导出以及高级修改、可启动 ISO 和 El Torito 检查、原创启动模板的 BPB 保留与备份、固定 VHD 临时浏览与清理、FAT 部署规划、尾部零扇区报告、原生拖放契约、全操作图形批处理编辑与无副作用预演、文档预览/查找/保存回写、目录分页遍历、完整七语言工作区、公共 API 会话、可移植设置、任务中心、字体与目录视图持久化、主题切换、跨平台光学介质识别、校验和、MBR 解析、自解压归档、物理写入保护、目录导出和 FAT 重建式整理。pytest 启用严格配置、严格标记和警告即错误；GUI 同时接受离屏启动验证。持续集成会在 Windows、Linux、macOS Intel 和 macOS Apple Silicon 上运行同一质量门槛，并打包每个原生目标。版本标签必须与项目元数据一致；若同版本 Release 已存在，工作流将失败而绝不会覆盖资产。

```bash
QT_QPA_PLATFORM=offscreen pytest
QT_QPA_PLATFORM=offscreen python scripts/gui_smoke.py
```

详细构建与发布说明参阅 [BUILDING.md](docs/BUILDING.md)，真实文件系统与 UFI 硬件的可选验收步骤参阅 [VALIDATION.md](docs/VALIDATION.md)。界面冒烟验证记录参阅 [gui_validation.md](artifacts/gui_validation.md)。

## 参与贡献

欢迎提交 Issue 和 Pull Request。请保持变更聚焦，为行为变化增加回归测试，且不要提交真实磁盘映像、凭据、私有路径或生成的构建产物。

## 许可证

DiskForge 采用 [MIT License](LICENSE) 发布。
