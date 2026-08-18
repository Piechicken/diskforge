# DiskForge

**DiskForge** 是一个原创的跨平台磁盘映像工作台，使用 Python 与 Qt 构建，提供可直接运行的 GUI 以及命令行入口。它围绕专业磁盘映像软件的完整工作流设计：创建与读取映像、目录浏览、提取和注入文件、格式转换、FAT 映像重建式碎片整理、启动扇区编辑、SHA-256 校验、批处理、目录导出/打印、自解压归档，以及带多重保护的物理磁盘读写。

> DiskForge 是独立实现，采用清晰、可审计的开源设计，围绕专业磁盘映像管理所需的创建、浏览、提取、转换、验证和安全写入工作流构建。

![已加载 FAT 映像的 DiskForge 工作区](assets/diskforge-workspace.png)

## 快速开始

| 目的 | 命令 |
|---|---|
| 从源码启动 GUI | `python -m pip install -e '.[dev]'`，随后执行 `diskforge` |
| 使用命令行 | `diskforge-cli --help` |
| 创建可编辑 FAT 映像 | `diskforge-cli create-fat demo.img --size-mib 32 --fat 16` |
| 从目录创建 ISO | `diskforge-cli create-iso ./folder demo.iso --label DEMO` |
| 检查映像 | `diskforge-cli info demo.img` |
| 本机打包 | `python scripts/build.py` |

项目要求 **Python 3.10+**。在 Windows、macOS 与 Linux 上安装相同的 Python 依赖即可运行 GUI；若使用打包脚本，应当在目标操作系统本机构建对应原生包。

## 图形界面

主窗口由左侧映像树、中间目录表格、右侧映像信息/活动日志及底部可取消进度区构成。菜单将破坏性操作与常用浏览操作分开：`Image` 菜单包含提取、注入、删除、FAT 文件时间属性、转换、SHA-256、FAT 碎片整理、分区查看、启动扇区编辑、目录导出、打印和自解压归档；`Tools` 菜单包含批处理与物理驱动器读写。

所有大文件操作以块流式读写，不会将整个映像一次装入内存。这样能够降低处理大容量映像时的内存占用，并使长任务可显示进度、支持取消和安全校验。

## 功能对照

| 专业映像工作流 | DiskForge 实现 | 状态与说明 |
|---|---|---|
| 从 USB、硬盘、分区或可移动盘读取映像 | 系统磁盘枚举，流式原始设备读取 | **已实现**；需要相应系统权限。 |
| 向物理盘写回映像 | 容量、挂载状态、系统盘检查；必须输入 `ERASE`；可写后校验 | **已实现并默认受保护**。 |
| 创建空映像 | RAW/IMG、FAT12、FAT16、FAT32；从目录创建 ISO9660/Joliet | **已实现**。 |
| 浏览与提取映像内容 | FAT12/16/32、ISO9660/Joliet 的目录树、批量提取 | **已实现**。 |
| 注入、删除文件/目录 | 可写 FAT 映像的递归注入与删除 | **已实现**。ISO 是只读介质，采用“从目录重建 ISO”工作流。 |
| 文件属性 | FAT 映像内选中项的修改时间编辑 | **已实现**。 |
| 映像格式转换 | RAW/IMG 与固定 VHD 原生转换；VHDX、VMDK、QCOW2 通过明确配置的 `qemu-img` | **已实现**；外部转换器不会被自动下载或静默执行。 |
| 映像碎片整理 | FAT 映像重建，按目录与文件顺序连续写入新映像 | **已实现**；原映像保持不变。 |
| MBR / GPT | MBR 主分区与 GPT 分区表解析、文件系统提示 | **已实现**。 |
| 启动扇区属性 | 512 字节十六进制查看/编辑、导入启动扇区、整映像备份后应用 | **已实现**。 |
| 目录导出与打印 | FAT 目录导出为 TXT/HTML；FAT/ISO 目录清单通过系统打印对话框输出 | **已实现**。 |
| 自解压映像 | 含 SHA-256 清单的跨平台 `.pyz` 自解压归档；可由打包流程封装为原生启动器 | **已实现**。 |
| 自动化 | 有模式校验、可审计、明确禁止无人值守物理盘写入的 JSON 批处理 | **已实现**。 |
| NTFS / EXT / DMG | 签名与分区提示；提供转换/扩展适配接口 | **受限**；当前原生读写重点是 FAT 和 ISO。此限制被明确暴露给 UI，而非伪装成可编辑。 |

DiskForge 优先原生实现安全且可完整测试的 FAT、ISO、RAW/IMG 和固定 VHD 工作流，同时将 VHDX、VMDK、QCOW2 交由可选的标准转换器处理。不能原生编辑的文件系统会明确显示为不可浏览/不可写，避免产生破坏性误操作。

## 映像格式

| 格式 | 原生检查 | 原生浏览/编辑 | 原生创建/转换 | 备注 |
|---|---:|---:|---:|---|
| RAW / IMG / IMA / BIN | 是 | FAT 内容可浏览编辑 | 是 | 以扇区流处理。 |
| FAT12 / FAT16 / FAT32 | 是 | 是 | 是 | 由 `pyfatfs` 提供 FAT 卷操作。 |
| ISO9660 / Joliet | 是 | 只读浏览与提取 | 从目录创建 | ISO 作为只读媒介对待。 |
| 固定 VHD | 是 | 载荷可转换 | 是 | 原生追加/校验 VHD footer。 |
| VHDX / VMDK / QCOW2 | 有可选转换器时 | 通过转换流程 | 有可选转换器时 | 在 Preferences 指定 `qemu-img`。 |
| DMG、NTFS、EXT | 签名提示 | 不提供原生修改 | 建议转为 RAW 后交由外部工具 | 不承诺未经测试的写入兼容性。 |

## 安全模型

物理设备写入是高风险操作。DiskForge **不会**自动挂载映像或自动写入任何设备。写盘前会拒绝系统盘、已挂载设备和容量不足的目标；用户还必须在界面中输入精确的 `ERASE` 短语。批处理模式故意拒绝所有物理盘写入，避免导入的脚本静默覆盖数据。启动扇区写入之前则会保存完整映像副本。

请先在不重要的测试映像上练习，再接触真实设备。对于重要介质，建议先“Read selected drive to image”，计算 SHA-256，并保留至少两份独立副本。

## 批处理

批处理采用 JSON，模式固定为 `diskforge.batch/v1`。支持映像转换和 SHA-256 校验；明确拒绝 `read_device` 与 `write_device` 等无人值守原始设备操作。可从 GUI 的 **Tools → Run batch recipe** 启动，也可用命令行执行：

```bash
diskforge-cli batch recipe.json
```

示例结构：

```json
{
  "schema": "diskforge.batch/v1",
  "operations": [
    {
      "name": "Convert IMG to VHD",
      "kind": "convert",
      "source": "archive.img",
      "destination": "archive.vhd",
      "format": "vhd"
    }
  ]
}
```

## 开发与验证

```bash
python -m pip install -e '.[dev]'
QT_QPA_PLATFORM=offscreen pytest
QT_QPA_PLATFORM=offscreen python scripts/gui_smoke.py
QT_QPA_PLATFORM=offscreen python scripts/gui_open_image_smoke.py
```

当前测试覆盖 FAT 创建、注入、提取、ISO 创建/提取、固定 VHD、哈希与字节校验、MBR 解析、自解压、物理写入保护、启动扇区备份、批处理限制、FAT 目录导出与重建式碎片整理。GUI 截图验证记录在 [`artifacts/gui_validation.md`](artifacts/gui_validation.md)。

## 许可证

本项目采用 [MIT License](LICENSE) 发布。
