# DiskForge 真实文件系统验收

**DiskForge 的常规测试不包含第三方二进制磁盘映像。** 这是为了保持源代码仓库轻量、可审查，并避免重新分发不属于项目的样本。与真实文件系统映像有关的回归是可选验收：只有在操作者自行取得相应样本、确认其许可并在本机安装 Sleuth Kit `fls` 和 `icat` 后才会执行。

> 真实样本验收确认的是 DiskForge 的**只读列举和数据 fork 提取**路径。另有独立的合成映像回归覆盖可选 NTFS/EXT/经典 HFS 受控注入，以及经典 HFS 的受限新建：它们只创建新输出映像并验证文件内容或签名，绝不修改源映像或物理设备。经典 HFS 注入只复制原始数据 fork；该范围不授权或实现 HFS+ 写入、文件系统修复、自动挂载、资源 fork 完整保留，也不保证每一种损坏、加密、压缩或专有容器变体均可读取。

## 可选夹具

| 文件名 | 用途 | 来源与许可 | DiskForge 调用方式 |
|---|---|---|---|
| `ntfs-lastaccess.raw` | NTFS 分区级列举与 `/test/1.txt` 提取 | `msuhanov/ntfs-samples`，仓库标示 CC0-1.0。[1] | `FileSystemType.NTFS`，显式偏移 `128 * 512` 字节。 |
| `fs.ext4` | EXT4 分区级列举与 `/audio1/debian.mp3` 提取 | `eribertomota/forensics-samples`，文件系统映像标示为 MIT 许可。[2] | `FileSystemType.EXT`，显式偏移 `2048 * 512` 字节。 |
| `nps-hfsj-image.gen1.dmg` | journaled HFS+ 根目录列举与 `/file1.txt` 数据 fork 提取 | Digital Corpora NPS 公共测试映像，目录为 10 MB。[3] [4] | `FileSystemType.HFS_PLUS`，偏移 0。 |

将文件放入一个**不受版本控制**的目录。不要将样本、从样本提取的个人数据或本地绝对路径提交到 DiskForge 仓库。

## 运行方式

在 Linux 或具备同等 Sleuth Kit 后端的环境中，设置样本目录后运行：

```bash
cd diskforge
export DISKFORGE_REAL_FS_FIXTURES=/absolute/path/to/fixtures
QT_QPA_PLATFORM=offscreen pytest -W error tests/test_real_readonly_samples.py
```

这会运行 `tests/test_real_readonly_samples.py`。当环境变量、所需样本或 Sleuth Kit 工具不可用时，测试会以明确的 `skipped` 状态结束；它不会下载样本、挂载映像、修改映像或把外部工具静默打包到程序中。

## v0.10 自动化老式映像与 ISO 验收

v0.10 的常规严格回归不需要稀缺物理软盘。它会创建并重新打开 15 个可验证的 PC 兼容 FAT12 profile：5.25 英寸 160/180/320/360/640/720 KiB 与 1.2 MiB，3.5 英寸 320/360/640/720 KiB、1.44 MiB、DMF 1.68 MiB、82 磁道 1,722 KiB 与 2.88 MiB。每个 profile 均验证输出 `.ima`/`.img` 格式、文件长度、FAT12 识别及 BPB 的扇区大小、每磁道扇区数和磁头字段。回归还验证 IMA 的注入、改名、DOS 属性、提取、SHA-256 以及 IMG/IMA 无损转换。

ISO 回归会验证标准、Rock Ridge、UDF 和组合 profile 的重建编辑；对于 El Torito，仅接受并复核可唯一映射的单初始启动条目。多节/多启动目录、混合系统区、启动映像或自动生成目录的修改、以及无法无歧义重建的映像均必须失败。此限制是可验证安全边界，而非对全部启动 ISO 变体的虚假兼容声明。

128/256 字节扇区、GCR、变速/变扇区、硬分区、非 FAT、复制保护与 flux/bitcell 格式不进入原生 FAT 创建断言；它们仍可按原始字节进行保存、校验、比较和受控转换。测试不会根据文件大小臆测这些格式的物理来源。

## v0.10 可选 NTFS/EXT/经典 HFS 受控注入与新建验收

NTFS、EXT 和经典 HFS 写入均不作为原生或跨平台保证。仅当本机明确提供所需外部后端时，常规回归才会对临时创建的独立映像执行该项验收：NTFS 使用 `mkntfs`、`ntfscp`、`ntfsls` 和 `ntfscat`；EXT 使用 `mke2fs`、`debugfs` 和 `e2fsck`；经典 HFS 使用 `hformat`、`hmount`、`hcopy` 和 `hls`。缺少任一可选工具时，对应集成用例以明确 `skipped` 状态结束；不下载、不打包任何外部二进制。[6] [7] [8] [9]

| 文件系统 | 合成验收 | 必须保持的边界 |
|---|---|---|
| NTFS | 创建 64 MiB 独立卷；`ntfscp -n` 预演；将新常规文件写入独立输出；用 `ntfscat` 读回 SHA-256，并重新计算源 SHA-256。 | 拒绝设备、分区偏移、已有目标、覆盖、目录、ADS、ACL、元数据、改名、删除及原位写入。 |
| EXT4 | 创建 64 MiB 独立卷；生成受限命令文件，由 `debugfs -w -f -z` 写入独立输出；`debugfs dump` 读回 SHA-256；`e2fsck -fn` 必须返回 0。 | 拒绝设备、分区偏移、已有目标、目录、链接、元数据、改名、删除及原位写入。 |
| 经典 HFS 注入 | 创建 800 KiB 独立卷；每次操作使用独立临时 `HOME`；在新副本挂载后，必须从 `hls -1 -N` 的 stderr 检出 `no such file or directory` 再执行 `hcopy -r`；逐项 `hcopy -r` 读回 SHA-256，并重算源 SHA-256。 | 拒绝设备、分区偏移、已有目标、目录、链接、冒号/通配符名称、MFS、HFS+、元数据、资源 fork、改名、删除及原位写入。 |
| 经典 HFS 新建 | 对新的 800 KiB、512 字节对齐临时常规文件执行 `hformat -l`；使用独立临时 `HOME`；验证 HFS 签名、大小和输出 SHA-256，再原子提升。核心、CLI JSON、图形新建对话框与 v4 `hfs_create` recipe 均有回归。 | 拒绝小于 800 KiB 或非 512 对齐大小、既有目标、设备路径、分区号、`-f`、分区映射、MFS、HFS+、物理介质和不安全卷标。 |

这些测试还覆盖 GUI 的新输出选择与自动打开、CLI 的 JSON 审计结果，以及批处理 v4 的 `ntfs_inject`/`ext_inject`/`hfs_inject`/`hfs_create` 预览和执行。HFS+ 仍不启用受控注入或新建动作。详细合同见 [FILESYSTEM_INJECTION.md](FILESYSTEM_INJECTION.md)。

## v0.10 显式只读分区浏览与目录报告验收

DiskForge 的 MBR/GPT 解析器先验证分区表，再只接受操作者指定的稳定一位索引；它不会扫描或推断“第一个可兼容分区”。FAT 分区保持已有的可写会话，而 NTFS、EXT、经典 HFS 与 HFS+ 分区仅由 Sleuth Kit `fls`/`icat` 在该分区的精确扇区偏移下打开。请求非 FAT 写入会在启动外部后端之前被拒绝；不挂载、不修改分区表、不写入源映像或物理设备。[8] [9]

| 验收层 | 自动化证据 | 必须保持的边界 |
|---|---|---|
| 核心路由 | 合成 MBR Linux 分区验证 EXT 类型与精确字节偏移；写入请求在后端调用前失败；未知类型拒绝。 | 仅 FAT 可请求写入；NTFS/EXT/HFS/HFS+ 永远只读，且必须显式选择索引。 |
| CLI 与 SDK | `list`、`extract`、`export-listing` 与 `DiskForgeClient.filesystem(..., partition_index=N)` 均将索引交给同一核心路由，并始终关闭会话。 | 不回退为 FAT 或 offset-0；无隐式选择、无自动挂载、无写入升级。 |
| GUI 与报告 | 分区对话框可选已验证非 FAT 分区；导出和打印通过统一完整遍历产生新的文本/HTML 本地报告。 | 报告只写入所选报告文件；注入、删除、改名及受控写入动作仍禁用。 |

通用目录报告回归还验证跨文件系统稳定排序、HTML 路径转义和取消时不创建输出文件。该机制仅序列化 `ImageFilesystem.walk_entries()` 的只读结果，不执行文件、脚本或映像内内容。

## v0.10 FAT 常规文件移动验收

FAT 跨目录移动仅接受一个映像内常规文件和一个**已经存在**的映像内目录。核心先标准化路径并在调用底层单文件移动前拒绝根目录、缺失源、缺失目标、非目录目标、同名目标、只读会话和目录源；成功后源路径消失、目标路径存在，提取后的载荷必须逐字节一致。相同目录中的改名仍由独立的 `rename()` 路径处理。

| 验收层 | 自动化证据 | 必须保持的边界 |
|---|---|---|
| FAT 核心 | 合成 FAT12/FAT16 映像验证移动后可提取的原始载荷、同名冲突、无效目标、根目录、目录源与只读拒绝。 | 不覆盖、不合并、不创建目标目录；目录移动被拒绝，因为通用目录实现是复制后删除而非原子移动。 |
| CLI 与 SDK | `move-fat IMAGE SOURCE_PATH TARGET_DIRECTORY` 输出 JSON `source`/`destination`；`DiskForgeClient.move_fat()` 返回新的映像内路径。 | 仅可写 FAT；可选显式 FAT 分区由既有验证路由处理；非 FAT 不升级为可写。 |
| 批处理与桌面 | schema v4 `move` 预览标记 `will_write: true`，执行后审计原映像；图形设计器序列化并回填映像、源条目、目标目录和分区索引；桌面动作仅在一个常规文件被选中且 FAT 会话可写时启用。 | 无人值守配方不接受设备；桌面不会对目录显示移动动作；全部七种界面语言均有无回退目录。 |

在当前开发检查点，完整严格命令 `QT_QPA_PLATFORM=offscreen pytest -W error` 的结果为 **336 passed, 3 skipped**，且没有警告。跳过项仍只对应可选的真实外部文件系统夹具，不影响上述合成 FAT 移动回归。

## UFI USB 软驱人工验收

Linux 上的受控 UFI USB 软驱格式化要求 `ufiformat`、相应权限、真正的 UFI 兼容设备以及可丢弃介质。DiskForge 仅在 sysfs 将 `/dev/sgN` 显式关联到已发现的可移动块设备时显示候选项；随后必须由 `ufiformat -i` 报告设备与可用容量。操作者必须选择报告中的一个容量并输入 `FORMAT_FLOPPY`；执行命令固定包含 `-V` 验证，且不会使用跳过安全检查的 `-F` 选项。[5]

UFI 格式化完成后，创建 FAT 文件系统是**独立操作**，需要再次选择设备和确认。没有真实硬件读写回验前，任何环境都不应声称已验证特定 USB 软驱型号或控制器。该实硬件步骤记录为后续设备兼容性证据，而不是 v1.0.0 功能对齐的阻塞条件。

## 本机已复现实例

下表记录开发环境中一次可复现的只读验收，仅作为环境证据，不替代用户在目标系统、目标设备或目标样本上的验证。

| 路径 | 后端 | 结果 |
|---|---|---|
| CC0 NTFS `ntfs-lastaccess.raw` | Sleuth Kit 4.12.1 | 在 LBA 128 处列举 `/test`，提取 `/test/1.txt`，143 字节。 |
| MIT EXT4 `fs.ext4` | Sleuth Kit 4.12.1 | 在 LBA 2048 处列举 `/audio1`，提取 `/audio1/debian.mp3`，69,727 字节。 |
| NPS journaled HFS+ `image.gen1.dmg` | Sleuth Kit 4.12.1 | 列举 `/file1.txt` 与 `/file2.txt`，提取 `/file1.txt`，28 字节。 |
| 合成 standalone NTFS | ntfs-3g/ntfsprogs 2022.10.3 | 预演并向新副本添加 `PAYLOAD.TXT`；读回哈希匹配且源 SHA-256 不变。 |
| 合成 standalone EXT4 | e2fsprogs 1.47.0 | 通过 `debugfs` undo 日志写入新副本；读回哈希匹配，`e2fsck -fn` 返回 0，源 SHA-256 不变。 |
| 合成 standalone 经典 HFS 注入 | hfsutils 3.2.6-16 | 创建 800 KiB 卷，在隔离 `HOME` 中经 `hmount`、`hcopy -r`、`hls` 运行；新副本读回哈希匹配，源 SHA-256 不变。`hls` 对不存在目标返回 0 但在 stderr 写出缺失诊断，因此该诊断而非退出码构成无覆盖预检。 |
| 合成 standalone 经典 HFS 新建 | hfsutils 3.2.6-16 | 将新的 819,200 字节常规文件格式化为 `DISKFORGE` 卷；`inspect_image()` 识别为 HFS，输出 SHA-256 与审计结果一致；818,176 字节文件被 hformat 明确拒绝，隔离状态仅产生私有 `.hcwd`。 |

## References

[1]: https://github.com/msuhanov/ntfs-samples "msuhanov/ntfs-samples"
[2]: https://github.com/eribertomota/forensics-samples "eribertomota/forensics-samples"
[3]: https://digitalcorpora.org/corpora/disk-images/ "Digital Corpora Disk Images"
[4]: https://downloads.digitalcorpora.org/corpora/drives/nps-2009-hfsjtest1/ "NPS HFS Journal Test Image Directory"
[5]: https://manpages.ubuntu.com/manpages/jammy/man8/ufiformat.8.html "ufiformat manual"
[6]: https://linux.die.net/man/8/ntfscp "ntfscp(8) — copy file to an NTFS volume"
[7]: https://manpages.debian.org/testing/e2fsprogs/debugfs.8.en.html "debugfs(8) — ext2/ext3/ext4 filesystem debugger"
[8]: https://manpages.ubuntu.com/manpages/bionic/man1/hfsutils.1.html "hfsutils(1) — classic HFS utility suite"
[9]: https://manpages.ubuntu.com/manpages/jammy/man1/hls.1.html "hls(1) — list files in an HFS directory"
[10]: https://manpages.ubuntu.com/manpages/jammy/man1/hformat.1.html "hformat(1) — create a new HFS filesystem"
