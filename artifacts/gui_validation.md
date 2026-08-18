# GUI 视觉冒烟验证

验证日期：2026-08-18。

在 `QT_QPA_PLATFORM=offscreen` 环境下，`scripts/gui_smoke.py` 成功生成空工作区截图，显示菜单栏、工具栏、映像树、目录表格、信息/活动面板与可取消进度区域均可初始化。`scripts/gui_open_image_smoke.py` 随后创建并打开了真实的 4 MiB FAT 映像，成功渲染根目录中的 `README.TXT`，并显示了路径、IMG 格式、4.0 MiB 物理大小、FAT16 检测结果、可写状态和扇区大小等元数据。

已验证截图：

- `artifacts/main-window.png`
- `artifacts/open-image-window.png`

这些验证确认 GUI 主窗口可实际启动并绑定核心映像服务，但不替代在 Windows、macOS 和真实物理设备上的人工验收。
