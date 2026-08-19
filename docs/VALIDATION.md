# DiskForge 真实文件系统验收

**DiskForge 的常规测试不包含第三方二进制磁盘映像。** 这是为了保持源代码仓库轻量、可审查，并避免重新分发不属于项目的样本。与真实文件系统映像有关的回归是可选验收：只有在操作者自行取得相应样本、确认其许可并在本机安装 Sleuth Kit `fls` 和 `icat` 后才会执行。

> 该验收确认的是 DiskForge 当前的**只读列举和数据 fork 提取**路径。它不授权或实现 NTFS、EXT、HFS 或 HFS+ 写入、修复、自动挂载、资源 fork 完整保留，也不保证每一种损坏、加密、压缩或专有容器变体均可读取。

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

## References

[1]: https://github.com/msuhanov/ntfs-samples "msuhanov/ntfs-samples"
[2]: https://github.com/eribertomota/forensics-samples "eribertomota/forensics-samples"
[3]: https://digitalcorpora.org/corpora/disk-images/ "Digital Corpora Disk Images"
[4]: https://downloads.digitalcorpora.org/corpora/drives/nps-2009-hfsjtest1/ "NPS HFS Journal Test Image Directory"
[5]: https://manpages.ubuntu.com/manpages/jammy/man8/ufiformat.8.html "ufiformat manual"
