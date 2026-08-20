"""DiskForge desktop interface built with Qt Widgets.

The UI is intentionally workflow-first: the image directory is always visible,
metadata is persistent, and destructive actions remain separated and clearly
labeled.  All large work is performed through ``FunctionWorker``.
"""
from __future__ import annotations

import os
import shutil
import tempfile
from datetime import datetime
from pathlib import Path
from typing import Callable, Sequence

from PySide6.QtCore import QDateTime, QMimeData, QSettings, QSize, Qt, QThreadPool, QUrl
from PySide6.QtGui import QAction, QActionGroup, QDrag, QFont, QKeySequence, QTextDocument
from PySide6.QtPrintSupport import QPrintDialog, QPrinter
from PySide6.QtWidgets import (
    QAbstractItemView, QApplication, QCheckBox, QComboBox, QDialog, QDialogButtonBox, QFontComboBox,
    QFileDialog, QFormLayout, QFrame, QGroupBox, QHBoxLayout, QHeaderView, QLabel,
    QLineEdit, QInputDialog, QListWidget, QListWidgetItem, QMainWindow, QMenu, QMessageBox, QPlainTextEdit, QProgressBar,
    QPushButton, QSpinBox, QDateTimeEdit, QSplitter, QStackedWidget, QStatusBar, QStyle, QTableWidget, QTableWidgetItem,
    QTabWidget, QTextBrowser, QToolBar, QTreeWidget, QTreeWidgetItem, QVBoxLayout,
    QWidget,
)

from diskforge.core.batch import BatchRunner
from diskforge.core.browse_session import BrowsableImageSession, materialize_browsable_image
from diskforge.core.bootsector import (apply_boot_template, backup_and_write_boot_sector,
                                       edit_fat_boot_properties, import_boot_sector_file, inspect_boot_sector, list_boot_templates,
                                       load_boot_sector_file, parse_hexdump, read_sector, sector_hexdump)
from diskforge.core.bundle import create_bundle
from diskforge.core.compare import compare_streams
from diskforge.core.device_queue import DeviceReadRequest, read_device_queue
from diskforge.core.devices import (backup_device_mbr, format_removable_fat, list_devices,
                                      neutralize_device_mbr, read_device_to_image, restore_device_mbr,
                                      write_image_to_device)
from diskforge.core.deployment import prepare_fat_deployment
from diskforge.core.ext_inject import ExtFileInjector
from diskforge.core.hfs_create import HfsImageCreator
from diskforge.core.hfs_inject import HfsFileInjector
from diskforge.core.eltorito import export_boot_image, inspect_eltorito
from diskforge.core.fat_layouts import FatImageLayout, create_fat_image_from_layout
from diskforge.core.floppy_format import FloppyControllerFormatter
from diskforge.core.filesystems import (FatImageFilesystem, ImageFilesystem, IsoImageFilesystem,
                                        create_fat_image, create_iso_from_directory, defragment_fat_image,
                                        rebuild_iso_with_changes, replace_iso_file_safely)
from diskforge.core.formats import (Dmg2ImgConverter, QemuImgConverter, convert_image, create_dynamic_vhd_from_raw,
                                     create_editable_fixed_vhd_copy, create_legacy_zip_image, inspect_image,
                                     validate_fixed_vhd_fat)
from diskforge.core.legacy_floppy import (LEGACY_FLOPPY_PROFILES, LegacyFloppyGeometry,
                                           create_legacy_fat_floppy,
                                           create_legacy_fat_floppy_profile)
from diskforge.core.listing import collect_directory_listing, directory_listing_html, export_directory_listing
from diskforge.core.media import create_dmf_image, trim_zero_tail, wrap_fat_image_in_mbr
from diskforge.core.mounts import ImageMountManager, ImageMountSession
from diskforge.core.ntfs_inject import NtfsFileInjector
from diskforge.core.metadata import load_image_metadata, save_image_comment
from diskforge.core.models import (ConflictPolicy, DeviceInfo, ExtractionLayout, ExtractionPolicy,
                                   DeviceKind, FileSystemType, ImageEntry, ImageFormat, OperationKind, Progress,
                                   human_bytes)
from diskforge.core.partition_filesystems import open_partition_filesystem
from diskforge.core.partitions import list_partitions
from diskforge.core.preview import inspect_file_preview
from diskforge.core.readonly_fs import SleuthKitImageFilesystem
from diskforge.core.resize import resize_image
from diskforge.core.selfextract import create_self_extractor
from diskforge.core.storage import DiskForgeError, sha256_file
from diskforge.gui.batch_designer import BatchDesignerDialog
from diskforge.gui.batch_results import BatchResultDialog
from diskforge.gui.dragdrop import ImageEntryList, ImageEntryTable
from diskforge.gui.i18n import LANGUAGES, language_manager
from diskforge.gui.preview import FilePreviewDialog
from diskforge.gui.theme import apply_theme
from diskforge.gui.workers import FunctionWorker


IMAGE_FILTER = "Disk images (*.img *.ima *.hfs *.bin *.dd *.dmf *.iso *.vhd *.vhdx *.vmdk *.qcow2 *.dmg);;All files (*)"


class NewImageDialog(QDialog):
    """Create native RAW/FAT or ISO image workflows without a wizard dependency."""

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.setWindowTitle("New image")
        self.setMinimumWidth(560)
        layout = QVBoxLayout(self)
        form = QFormLayout()
        self.kind = QComboBox()
        self.kind.addItem("FAT image (editable)", "fat")
        self.kind.addItem("FAT image from template layout", "fat_layout")
        self.kind.addItem("Raw/IMG image", "raw")
        self.kind.addItem("Legacy FAT floppy image (IMG/IMA)", "legacy_floppy")
        self.kind.addItem("DMF 1.68 MB FAT12 image", "dmf")
        self.kind.addItem("Classic HFS image (optional hfsutils)", "hfs")
        self.kind.addItem("ISO9660/Joliet from directory", "iso")
        self.size = QSpinBox()
        self.size.setRange(1, 1024 * 1024)
        self.size.setValue(32)
        self.size.setSuffix(" MiB")
        self.fat = QComboBox()
        self.fat.addItems(["FAT12", "FAT16", "FAT32"])
        self.label = QLineEdit("DISKFORGE")
        self.source = QLineEdit()
        self.source_button = QPushButton("Browse…")
        self.source_button.clicked.connect(self._choose_source)
        source_row = QHBoxLayout()
        source_row.addWidget(self.source)
        source_row.addWidget(self.source_button)
        form.addRow("Image type", self.kind)
        form.addRow("Size", self.size)
        self.hfs_size_label = QLabel("Classic HFS size")
        self.hfs_size = QSpinBox()
        self.hfs_size.setRange(800, 1024 * 1024)
        self.hfs_size.setValue(800)
        self.hfs_size.setSuffix(" KiB")
        form.addRow(self.hfs_size_label, self.hfs_size)
        form.addRow("FAT variant", self.fat)
        form.addRow("Volume label", self.label)
        self.legacy_profile_label = QLabel("Legacy floppy profile")
        self.legacy_profile = QComboBox()
        for profile in LEGACY_FLOPPY_PROFILES:
            self.legacy_profile.addItem(profile.description, profile.identifier)
        self.legacy_format_label = QLabel("Legacy image format")
        self.legacy_format = QComboBox()
        self.legacy_format.addItem("IMA floppy image (.ima)", ImageFormat.IMA)
        self.legacy_format.addItem("IMG raw image (.img)", ImageFormat.IMG)
        self.legacy_custom = QCheckBox("Use custom legacy geometry")
        self.legacy_cylinders = QSpinBox()
        self.legacy_cylinders.setRange(1, 0xFFFF)
        self.legacy_cylinders.setValue(80)
        self.legacy_heads = QSpinBox()
        self.legacy_heads.setRange(1, 0xFFFF)
        self.legacy_heads.setValue(2)
        self.legacy_sectors = QSpinBox()
        self.legacy_sectors.setRange(1, 0xFFFF)
        self.legacy_sectors.setValue(9)
        self.legacy_sector_size = QComboBox()
        for value in (512, 1024, 2048, 4096):
            self.legacy_sector_size.addItem(f"{value} bytes", value)
        custom_geometry = QHBoxLayout()
        custom_geometry.addWidget(QLabel("C"))
        custom_geometry.addWidget(self.legacy_cylinders)
        custom_geometry.addWidget(QLabel("H"))
        custom_geometry.addWidget(self.legacy_heads)
        custom_geometry.addWidget(QLabel("S"))
        custom_geometry.addWidget(self.legacy_sectors)
        custom_geometry.addWidget(QLabel("Bytes/sector"))
        custom_geometry.addWidget(self.legacy_sector_size)
        self.legacy_geometry_label = QLabel("Custom CHS geometry")
        self.legacy_geometry_widget = QWidget()
        self.legacy_geometry_widget.setLayout(custom_geometry)
        form.addRow(self.legacy_profile_label, self.legacy_profile)
        form.addRow(self.legacy_format_label, self.legacy_format)
        form.addRow("", self.legacy_custom)
        form.addRow(self.legacy_geometry_label, self.legacy_geometry_widget)
        self.source_label = QLabel("ISO source folder")
        form.addRow(self.source_label, source_row)
        self.boot_image = QLineEdit()
        boot_button = QPushButton("Browse…")
        boot_button.clicked.connect(self._choose_boot_image)
        boot_row = QHBoxLayout()
        boot_row.addWidget(self.boot_image)
        boot_row.addWidget(boot_button)
        self.boot_media = QComboBox()
        self.boot_media.addItem("No emulation", "noemul")
        self.boot_media.addItem("Floppy emulation", "floppy")
        self.boot_media.addItem("Hard-disk emulation", "hdemul")
        self.boot_info_table = QCheckBox("Write boot info table into the ISO copy")
        self.rock_ridge = QCheckBox("Include Rock Ridge names")
        self.udf = QCheckBox("Include UDF bridge filesystem")
        form.addRow("Optional ISO boot image", boot_row)
        form.addRow("Boot media mode", self.boot_media)
        form.addRow("", self.boot_info_table)
        form.addRow("", self.rock_ridge)
        form.addRow("", self.udf)
        layout.addLayout(form)
        self.help = QLabel("FAT images can be browsed and modified immediately.")
        self.help.setWordWrap(True)
        layout.addWidget(self.help)
        buttons = QDialogButtonBox(QDialogButtonBox.StandardButton.Ok | QDialogButtonBox.StandardButton.Cancel)
        buttons.accepted.connect(self.accept)
        buttons.rejected.connect(self.reject)
        layout.addWidget(buttons)
        self.kind.currentIndexChanged.connect(self._update_controls)
        self.legacy_custom.toggled.connect(self._update_controls)
        self._update_controls()

    @staticmethod
    def _localized(source: str) -> str:
        """Translate a source string while keeping isolated GUI tests operable."""
        try:
            return language_manager().text(source)
        except RuntimeError:
            return source

    @staticmethod
    def _set_translatable_label(label: QLabel, source: str) -> None:
        """Render a dynamic label using the source-string translation contract."""
        translated = NewImageDialog._localized(source)
        label.setProperty("df_source_text", source)
        label.setProperty("df_source_text_rendered", translated)
        label.setText(translated)

    def _choose_source(self) -> None:
        if self.kind.currentData() == "fat_layout":
            choice, _ = QFileDialog.getOpenFileName(
                self, "Choose FAT layout template", "", "FAT images (*.img *.ima *.dmf *.bin);;All files (*)",
            )
        else:
            choice = QFileDialog.getExistingDirectory(self, "Choose source directory")
        if choice:
            self.source.setText(choice)

    def _choose_boot_image(self) -> None:
        choice, _ = QFileDialog.getOpenFileName(self, "Choose El Torito boot image", "", "Boot image (*.img *.ima *.bin);;All files (*)")
        if choice:
            self.boot_image.setText(choice)

    def _update_controls(self) -> None:
        mode = self.kind.currentData()
        is_iso = mode == "iso"
        is_layout = mode == "fat_layout"
        is_legacy = mode == "legacy_floppy"
        is_hfs = mode == "hfs"
        self.size.setEnabled(mode not in {"iso", "dmf", "fat_layout", "legacy_floppy", "hfs"})
        self.hfs_size_label.setVisible(is_hfs)
        self.hfs_size.setVisible(is_hfs)
        self.fat.setEnabled(mode == "fat")
        for widget in (self.legacy_profile_label, self.legacy_profile, self.legacy_format_label, self.legacy_format,
                       self.legacy_custom, self.legacy_geometry_label, self.legacy_geometry_widget):
            widget.setVisible(is_legacy)
        custom_legacy = is_legacy and self.legacy_custom.isChecked()
        self.legacy_profile.setEnabled(is_legacy and not custom_legacy)
        self.legacy_geometry_widget.setEnabled(custom_legacy)
        self.source.setEnabled(is_iso or is_layout)
        self.source_button.setEnabled(is_iso or is_layout)
        self._set_translatable_label(self.source_label, "FAT layout template" if is_layout else "ISO source folder")
        self.boot_image.setEnabled(is_iso)
        self.boot_media.setEnabled(is_iso)
        self.boot_info_table.setEnabled(is_iso)
        self.rock_ridge.setEnabled(is_iso)
        self.udf.setEnabled(is_iso)
        if mode == "iso":
            self._set_translatable_label(self.help, "ISO files are authored from a local directory and are read-only after creation.")
        elif mode == "raw":
            self._set_translatable_label(self.help, "Raw images are sparse zero-filled files; format them externally or write sectors manually.")
        elif mode == "legacy_floppy":
            self._set_translatable_label(self.help, "Creates an editable FAT12 IMG or IMA with an explicit legacy floppy profile or custom geometry. The size is shown in KiB; no physical device is formatted.")
        elif mode == "dmf":
            self._set_translatable_label(self.help, "Creates an 80×2×21-sector FAT12 image file. Physical floppy formatting is not performed.")
        elif mode == "fat_layout":
            self._set_translatable_label(self.help, "Reads a valid FAT BPB layout from a template image and creates a new editable image; the template is never modified.")
        elif mode == "hfs":
            self._set_translatable_label(self.help, "Creates a new standalone classic HFS file through an explicitly available hfsutils backend. The output is verified before opening; HFS+ and physical media are not included.")
        else:
            self._set_translatable_label(self.help, "FAT images are editable and support file injection, deletion and timestamp changes.")


class ConvertDialog(QDialog):
    def __init__(self, source: Path, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.source = source
        self.setWindowTitle("Convert image")
        form = QFormLayout(self)
        self.format = QComboBox()
        self.format.addItem("Raw IMG image (.img)", ImageFormat.IMG)
        self.format.addItem("IMA floppy image (.ima)", ImageFormat.IMA)
        self.format.addItem("Fixed VHD (.vhd)", ImageFormat.VHD)
        self.format.addItem("VHDX (.vhdx, requires qemu-img)", ImageFormat.VHDX)
        self.format.addItem("VMware VMDK (.vmdk, requires qemu-img)", ImageFormat.VMDK)
        self.format.addItem("QEMU QCOW2 (.qcow2, requires qemu-img)", ImageFormat.QCOW2)
        self.destination = QLineEdit(str(source.with_suffix(".img")))
        browse = QPushButton("Browse…")
        browse.clicked.connect(self._choose_destination)
        row = QHBoxLayout()
        row.addWidget(self.destination)
        row.addWidget(browse)
        self.overwrite = QCheckBox("Allow overwrite")
        form.addRow("Target format", self.format)
        form.addRow("Destination", row)
        form.addRow("", self.overwrite)
        buttons = QDialogButtonBox(QDialogButtonBox.StandardButton.Ok | QDialogButtonBox.StandardButton.Cancel)
        buttons.accepted.connect(self.accept)
        buttons.rejected.connect(self.reject)
        form.addRow(buttons)
        self.format.currentIndexChanged.connect(self._suggest_extension)

    def _suggest_extension(self) -> None:
        value = ImageFormat(str(self.format.currentData()))
        suffix = ".img" if value == ImageFormat.IMG else f".{value.value}"
        self.destination.setText(str(self.source.with_suffix(suffix)))

    def _choose_destination(self) -> None:
        output, _ = QFileDialog.getSaveFileName(self, "Convert image", self.destination.text(), "All files (*)")
        if output:
            self.destination.setText(output)


class BootSectorDialog(QDialog):
    def __init__(self, image: Path, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.image = image
        self.setWindowTitle(f"Boot sector — {image.name}")
        self.resize(760, 620)
        layout = QVBoxLayout(self)
        self.details = QLabel()
        self.details.setWordWrap(True)
        layout.addWidget(self.details)
        self.editor = QPlainTextEdit()
        self.editor.setLineWrapMode(QPlainTextEdit.LineWrapMode.NoWrap)
        layout.addWidget(self.editor, 1)
        row = QHBoxLayout()
        load = QPushButton("Load 512-byte file…")
        load.clicked.connect(self._load_file)
        import_code = QPushButton("Import boot code safely…")
        import_code.clicked.connect(self._import_boot_code)
        reload_button = QPushButton("Reload")
        reload_button.clicked.connect(self._reload)
        save = QPushButton("Backup and apply")
        save.clicked.connect(self._save)
        self.template = QComboBox()
        for item in list_boot_templates():
            self.template.addItem(item.name, item)
        apply_template = QPushButton("Apply original template…")
        apply_template.clicked.connect(self._apply_template)
        row.addWidget(load)
        row.addWidget(import_code)
        row.addWidget(reload_button)
        row.addWidget(self.template)
        row.addWidget(apply_template)
        row.addStretch()
        row.addWidget(save)
        layout.addLayout(row)
        self._reload()

    def _reload(self) -> None:
        data = read_sector(self.image, 0)
        info = inspect_boot_sector(data)
        self.details.setText(
            f"OEM: <b>{info.oem_name or '—'}</b> · Filesystem: <b>{info.filesystem_label or 'unknown'}</b> · "
            f"Label: <b>{info.volume_label or '—'}</b> · Signature: <b>{'valid' if info.signature_valid else 'missing'}</b>"
        )
        self.editor.setPlainText(sector_hexdump(data))

    def _load_file(self) -> None:
        path, _ = QFileDialog.getOpenFileName(self, "Load boot sector", "", "Boot sector (*.bin *.img);;All files (*)")
        if path:
            self.editor.setPlainText(sector_hexdump(load_boot_sector_file(path)))

    def _import_boot_code(self) -> None:
        path, _ = QFileDialog.getOpenFileName(self, "Import boot-sector file", "", "Boot sector (*.bin *.img);;All files (*)")
        if not path:
            return
        answer = QMessageBox.warning(
            self, "Import boot code safely",
            "The file must be a signed 512-byte boot sector. Only its executable boot-code area will be imported; the current FAT BPB is preserved and a complete image backup is created first. Continue?",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.Cancel, QMessageBox.StandardButton.Cancel,
        )
        if answer != QMessageBox.StandardButton.Yes:
            return
        try:
            _, backup = import_boot_sector_file(self.image, Path(path))
            QMessageBox.information(self, "Boot code imported", f"Boot code imported safely. Backup created:\n{backup}")
            self._reload()
        except Exception as exc:
            QMessageBox.critical(self, "Unable to import boot code", str(exc))

    def _apply_template(self) -> None:
        template = self.template.currentData()
        if template is None:
            return
        answer = QMessageBox.warning(
            self, "Apply original boot template",
            f"Apply '{template.name}'? This replaces only the executable boot-code area, preserves the FAT BPB, and first creates a complete image backup.",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.Cancel, QMessageBox.StandardButton.Cancel,
        )
        if answer != QMessageBox.StandardButton.Yes:
            return
        try:
            _, backup = apply_boot_template(self.image, template.identifier)
            QMessageBox.information(self, "Boot template applied", f"Template applied. Backup created:\n{backup}")
            self._reload()
        except Exception as exc:
            QMessageBox.critical(self, "Unable to apply boot template", str(exc))

    def _save(self) -> None:
        try:
            payload = parse_hexdump(self.editor.toPlainText())
            answer = QMessageBox.warning(self, "Replace boot sector", "A full image backup of the current file will be created first. Continue?", QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.Cancel, QMessageBox.StandardButton.Cancel)
            if answer != QMessageBox.StandardButton.Yes:
                return
            backup = backup_and_write_boot_sector(self.image, payload)
            QMessageBox.information(self, "Boot sector applied", f"Boot sector updated. Backup created:\n{backup}")
            self.accept()
        except Exception as exc:
            QMessageBox.critical(self, "Unable to write boot sector", str(exc))


class DeviceDialog(QDialog):
    """Explicit device read/write confirmation dialog."""

    def __init__(self, image: Path | None, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.image = image
        self.devices: list[DeviceInfo] = []
        self.setWindowTitle("Physical drive operations")
        self.resize(700, 420)
        layout = QVBoxLayout(self)
        warning = QLabel("<b>Physical drive operations can destroy data.</b> System disks and mounted targets are rejected. Write operations require the exact confirmation phrase <b>ERASE</b>.")
        warning.setWordWrap(True)
        warning.setStyleSheet("color: #B54708;")
        layout.addWidget(warning)
        self.device_combo = QComboBox()
        layout.addWidget(self.device_combo)
        form = QFormLayout()
        self.image_path = QLineEdit(str(image) if image else "")
        choose = QPushButton("Browse…")
        choose.clicked.connect(self._choose_image)
        image_row = QHBoxLayout()
        image_row.addWidget(self.image_path)
        image_row.addWidget(choose)
        self.phrase = QLineEdit()
        self.phrase.setPlaceholderText("Required only to write a drive")
        self.verify = QCheckBox("Verify sectors after write")
        self.verify.setChecked(True)
        form.addRow("Image", image_row)
        form.addRow("Type ERASE to write", self.phrase)
        form.addRow("", self.verify)
        self.format_fat = QComboBox()
        self.format_fat.addItems(["FAT12", "FAT16", "FAT32"])
        self.format_label = QLineEdit("DISKFORGE")
        self.format_phrase = QLineEdit()
        self.format_phrase.setPlaceholderText("Type FORMAT to erase and format removable media")
        self.floppy_phrase = QLineEdit()
        self.floppy_phrase.setPlaceholderText("Type FORMAT_FLOPPY for controller-level floppy formatting")
        form.addRow("Removable format filesystem", self.format_fat)
        form.addRow("Removable format label", self.format_label)
        form.addRow("Type FORMAT to format", self.format_phrase)
        form.addRow("Type FORMAT_FLOPPY for controller format", self.floppy_phrase)
        layout.addLayout(form)
        actions = QHBoxLayout()
        read = QPushButton("Read selected drive to image…")
        read.clicked.connect(self._read)
        write = QPushButton("Write image to selected drive")
        write.setStyleSheet("font-weight: 700; color: #B42318;")
        write.clicked.connect(self._write)
        close = QPushButton("Close")
        close.clicked.connect(self.reject)
        actions.addWidget(read)
        actions.addWidget(write)
        backup_mbr = QPushButton("Back up selected MBR…")
        backup_mbr.clicked.connect(self._backup_mbr)
        neutralize_mbr = QPushButton("Neutralize selected MBR")
        neutralize_mbr.clicked.connect(self._neutralize_mbr)
        restore_mbr = QPushButton("Restore selected MBR…")
        restore_mbr.clicked.connect(self._restore_mbr)
        format_fat = QPushButton("Format removable FAT media")
        format_fat.setStyleSheet("font-weight: 700; color: #B42318;")
        format_fat.clicked.connect(self._format_removable_fat)
        format_floppy = QPushButton("Format controller floppy")
        format_floppy.setStyleSheet("font-weight: 700; color: #B42318;")
        format_floppy.clicked.connect(self._format_controller_floppy)
        format_ufi_floppy = QPushButton("Format UFI USB floppy")
        format_ufi_floppy.setStyleSheet("font-weight: 700; color: #B42318;")
        format_ufi_floppy.clicked.connect(self._format_ufi_floppy)
        actions.addWidget(backup_mbr)
        actions.addWidget(neutralize_mbr)
        actions.addWidget(restore_mbr)
        actions.addWidget(format_fat)
        actions.addWidget(format_floppy)
        actions.addWidget(format_ufi_floppy)
        actions.addStretch()
        actions.addWidget(close)
        layout.addLayout(actions)
        self._refresh()

    def _refresh(self) -> None:
        self.devices = list_devices()
        self.device_combo.clear()
        for item in self.devices:
            status = "SYSTEM" if item.system_disk else "optical / read-only" if item.kind == DeviceKind.OPTICAL else "mounted" if item.mounted else "safe candidate"
            self.device_combo.addItem(f"{item.display_name} — {human_bytes(item.size)} — {status} ({item.identifier})", item)

    def _choose_image(self) -> None:
        path, _ = QFileDialog.getOpenFileName(self, "Choose image", self.image_path.text(), IMAGE_FILTER)
        if path:
            self.image_path.setText(path)

    def _selected(self) -> DeviceInfo | None:
        return self.device_combo.currentData()

    def _read(self) -> None:
        device = self._selected()
        if not device:
            return
        suffix = ".iso" if device.kind == DeviceKind.OPTICAL else ".img"
        title = "Read optical media to ISO" if device.kind == DeviceKind.OPTICAL else "Read drive to image"
        path, _ = QFileDialog.getSaveFileName(self, title, f"{device.display_name}{suffix}", "ISO image (*.iso);;Raw image (*.img);;All files (*)")
        if path:
            self.done(10)
            self.setProperty("operation", ("read", device, Path(path)))

    def _backup_mbr(self) -> None:
        device = self._selected()
        if not device:
            return
        path, _ = QFileDialog.getSaveFileName(self, "Back up selected device MBR", "device.mbr", "MBR sector (*.mbr *.bin)")
        if path:
            self.done(12)
            self.setProperty("operation", ("mbr_backup", device, Path(path)))

    def _neutralize_mbr(self) -> None:
        device = self._selected()
        if not device:
            return
        if self.phrase.text() != "ERASE":
            QMessageBox.warning(self, "Confirmation required", "Type ERASE exactly before changing a device MBR.")
            return
        path, _ = QFileDialog.getSaveFileName(self, "Back up current MBR before neutralizing", "pre-neutralize.mbr", "MBR sector (*.mbr *.bin)")
        if path:
            self.done(13)
            self.setProperty("operation", ("mbr_neutralize", device, Path(path), self.phrase.text()))

    def _restore_mbr(self) -> None:
        device = self._selected()
        if not device:
            return
        if self.phrase.text() != "ERASE":
            QMessageBox.warning(self, "Confirmation required", "Type ERASE exactly before changing a device MBR.")
            return
        backup, _ = QFileDialog.getOpenFileName(self, "Select MBR backup to restore", "", "MBR sector (*.mbr *.bin);;All files (*)")
        if not backup:
            return
        pre_restore, _ = QFileDialog.getSaveFileName(self, "Back up current MBR before restoring", "pre-restore.mbr", "MBR sector (*.mbr *.bin)")
        if pre_restore:
            self.done(15)
            self.setProperty("operation", ("mbr_restore", device, Path(backup), Path(pre_restore), self.phrase.text()))

    def _format_controller_floppy(self) -> None:
        device = self._selected()
        if not device:
            return
        if self.floppy_phrase.text() != "FORMAT_FLOPPY":
            QMessageBox.warning(self, "Confirmation required", "Type FORMAT_FLOPPY exactly before controller-level floppy formatting.")
            return
        self.done(16)
        self.setProperty("operation", ("format_controller_floppy", device, self.floppy_phrase.text()))

    def _format_ufi_floppy(self) -> None:
        device = self._selected()
        if not device:
            return
        if self.floppy_phrase.text() != "FORMAT_FLOPPY":
            QMessageBox.warning(self, "Confirmation required", "Type FORMAT_FLOPPY exactly before UFI USB floppy formatting.")
            return
        try:
            discovery = FloppyControllerFormatter().discover_usb(device)
        except DiskForgeError as exc:
            QMessageBox.warning(self, "UFI USB floppy unavailable", str(exc))
            return
        values = [str(capacity) for capacity in discovery.supported_capacities]
        selected, accepted = QInputDialog.getItem(self, "Select UFI USB floppy capacity",
                                                   "Choose exactly one capacity reported by the device:", values, 0, False)
        if not accepted or not selected:
            return
        self.done(17)
        self.setProperty("operation", ("format_ufi_floppy", device, int(selected), self.floppy_phrase.text()))

    def _format_removable_fat(self) -> None:
        device = self._selected()
        if not device:
            return
        if self.format_phrase.text() != "FORMAT":
            QMessageBox.warning(self, "Confirmation required", "Type FORMAT exactly before formatting removable media.")
            return
        self.done(14)
        self.setProperty("operation", ("format_removable_fat", device, FileSystemType(self.format_fat.currentText()),
                                        self.format_label.text(), self.format_phrase.text()))

    def _write(self) -> None:
        device = self._selected()
        path = Path(self.image_path.text()) if self.image_path.text() else None
        if not device or not path or not path.is_file():
            QMessageBox.warning(self, "Missing image", "Choose a valid image and target device.")
            return
        if device.kind == DeviceKind.OPTICAL:
            QMessageBox.warning(self, "Read-only optical media", "Optical media can be read to an ISO file but are not writable through DiskForge.")
            return
        if self.phrase.text().strip().upper() != "ERASE":
            QMessageBox.warning(self, "Confirmation required", "Type ERASE exactly before writing a physical device.")
            return
        self.done(11)
        self.setProperty("operation", ("write", device, path, self.phrase.text(), self.verify.isChecked()))


class MainWindow(QMainWindow):
    @staticmethod
    def _localized(source: str) -> str:
        """Translate a source string without requiring global GUI bootstrap in tests."""
        try:
            return language_manager().text(source)
        except RuntimeError:
            return source

    def __init__(self, settings: QSettings | None = None) -> None:
        super().__init__()
        self.settings = settings or QSettings("DiskForge", "DiskForge")
        apply_theme(QApplication.instance(), str(self.settings.value("appearance", "light")))
        self._apply_interface_font()
        self.thread_pool = QThreadPool.globalInstance()
        self.current_path: Path | None = None
        self.current_info = None
        self.current_fs: ImageFilesystem | None = None
        self.current_browse_session: BrowsableImageSession | None = None
        self._editable_fixed_vhd = False
        self.current_partition_index: int | None = None
        self.current_mount_session: ImageMountSession | None = None
        self.current_directory = "/"
        self.current_entries: list[ImageEntry] = []
        self._directory_page_size = 250
        self._directory_total = 0
        self._directory_sort_by = "name"
        self._directory_sort_ascending = True
        self.current_worker: FunctionWorker | None = None
        self._task_items: dict[int, QTreeWidgetItem] = {}
        self._preview_directories: list[Path] = []
        self._active_preview_entry_path: str | None = None
        self.setWindowTitle("DiskForge — Disk Image Studio")
        self.resize(1280, 790)
        self._build_actions()
        self._build_menu()
        self._build_toolbar()
        self._build_layout()
        self._build_statusbar()
        self._restore_state()
        self._update_action_state()
        self.log("DiskForge ready. Open an image or create a new FAT/ISO image.")

    def _build_actions(self) -> None:
        self.action_new = self._action("New image…", "Ctrl+N", self.new_image)
        self.action_open = self._action("Open image…", "Ctrl+O", self.open_image)
        self.action_close = self._action("Close image", "Ctrl+W", self.close_image)
        self.action_extract = self._action("Extract selected…", "Ctrl+E", self.extract_selected)
        self.action_inject = self._action("Inject files…", "Ctrl+I", self.inject_files)
        self.action_controlled_inject = self._action("Inject files safely into new NTFS/EXT/classic HFS image…", None, self.inject_files_safely)
        self.action_delete = self._action("Delete selected", "Delete", self.delete_selected)
        self.action_properties = self._action("Modify selected timestamp…", None, self.modify_timestamp)
        self.action_rename = self._action("Rename selected…", "F2", self.rename_selected)
        self.action_attributes = self._action("Edit DOS attributes…", None, self.edit_attributes)
        self.action_label = self._action("Change volume label…", None, self.change_volume_label)
        self.action_comment = self._action("Edit image comment…", None, self.edit_image_comment)
        self.action_resize = self._action("Resize image…", None, self.resize_current_image)
        self.action_compare = self._action("Compare image…", None, self.compare_current_image)
        self.action_bundle = self._action("Create secure image bundle…", None, self.create_bundle)
        self.action_wrap_mbr = self._action("Wrap FAT image in MBR…", None, self.wrap_current_fat_in_mbr)
        self.action_prepare_deployment = self._action("Prepare FAT deployment image…", None, self.prepare_current_fat_deployment)
        self.action_trim_zero_tail = self._action("Trim trailing zero sectors…", None, self.trim_current_zero_tail)
        self.action_iso_boot = self._action("Inspect / export ISO boot image…", None, self.inspect_iso_boot)
        self.action_replace_iso = self._action("Safely replace ISO file…", None, self.replace_iso_file)
        self.action_edit_iso = self._action("Edit ISO content safely…", None, self.edit_standard_iso)
        self.action_editable_vhd = self._action("Create editable fixed VHD copy…", None, self.create_editable_vhd_copy)
        self.action_dynamic_vhd = self._action("Create dynamic VHD from FAT work image…", None, self.create_dynamic_vhd)
        self.action_convert_dmg = self._action("Convert DMG to raw image…", None, self.convert_dmg_image)
        self.action_mount = self._action("Mount image read-only…", None, self.mount_current_image)
        self.action_unmount = self._action("Unmount image", None, self.unmount_current_image)
        self.action_up = self._action("Up", "Alt+Up", self.go_up)
        self.action_convert = self._action("Convert image…", None, self.convert_image)
        self.action_verify = self._action("Verify SHA-256", None, self.verify_image)
        self.action_export = self._action("Export directory listing…", None, self.export_listing)
        self.action_print = self._action("Print directory listing…", None, self.print_listing)
        self.action_defragment = self._action("Defragment FAT image…", None, self.defragment_image)
        self.action_boot = self._action("Edit boot sector…", None, self.edit_boot_sector)
        self.action_devices = self._action("Read / write physical drive…", None, self.physical_drive)
        self.action_device_read_queue = self._action("Batch read physical media…", None, self.batch_read_physical_media)
        self.action_batch = self._action("Run batch recipe…", None, self.run_batch)
        self.action_batch_designer = self._action("Design batch workflow…", None, self.design_batch)
        self.action_batch_edit = self._action("Edit batch recipe…", None, self.edit_batch)
        self.action_sfx = self._action("Create self-extracting bundle…", None, self.create_sfx)
        self.action_legacy_zip = self._action("Create ZIP-compatible legacy image…", None, self.create_legacy_zip)
        self.action_preview = self._action("Preview selected file", "Return", self.preview_selected)
        self.action_view_details = self._action("Details view", None, lambda: self.set_view_mode("details"))
        self.action_view_icons = self._action("Icon view", None, lambda: self.set_view_mode("icons"))
        self.view_actions = QActionGroup(self)
        self.view_actions.setExclusive(True)
        for action, mode in ((self.action_view_details, "details"), (self.action_view_icons, "icons")):
            action.setCheckable(True)
            action.setData(mode)
            self.view_actions.addAction(action)
        self.action_partitions = self._action("View partitions", None, self.show_partitions)
        self.action_preferences = self._action("Preferences…", None, self.preferences)
        self.action_about = self._action("About DiskForge", None, self.about)

    def _action(self, text: str, shortcut: str | None, slot: Callable[[], None]) -> QAction:
        action = QAction(text, self)
        if shortcut:
            action.setShortcut(QKeySequence(shortcut))
        action.triggered.connect(slot)
        return action

    def _build_menu(self) -> None:
        menu_file = self.menuBar().addMenu("&File")
        menu_file.addActions([self.action_new, self.action_open, self.action_close])
        self.recent_menu = menu_file.addMenu("Open recent")
        self.recent_menu.aboutToShow.connect(self._populate_recent_menu)
        menu_file.addSeparator()
        menu_file.addAction("Exit", self.close)
        menu_image = self.menuBar().addMenu("&Image")
        menu_image.addActions([self.action_extract, self.action_inject, self.action_controlled_inject, self.action_preview, self.action_delete, self.action_properties,
                               self.action_rename, self.action_attributes, self.action_label, self.action_comment])
        menu_image.addSeparator()
        menu_image.addActions([self.action_convert, self.action_resize, self.action_trim_zero_tail, self.action_compare, self.action_verify,
                               self.action_defragment, self.action_partitions, self.action_boot, self.action_wrap_mbr, self.action_prepare_deployment,
                               self.action_iso_boot, self.action_replace_iso, self.action_edit_iso, self.action_editable_vhd, self.action_dynamic_vhd, self.action_convert_dmg,
                               self.action_mount, self.action_unmount])

        menu_image.addSeparator()
        menu_image.addActions([self.action_export, self.action_print, self.action_bundle, self.action_sfx, self.action_legacy_zip])
        menu_view = self.menuBar().addMenu("&View")
        menu_view.addActions([self.action_view_details, self.action_view_icons])
        menu_tools = self.menuBar().addMenu("&Tools")
        menu_tools.addActions([self.action_devices, self.action_device_read_queue, self.action_batch_designer, self.action_batch_edit, self.action_batch, self.action_preferences])
        menu_language = menu_tools.addMenu("&Language")
        self.language_actions: list[QAction] = []
        try:
            active_language = language_manager().language.code
        except RuntimeError:
            active_language = "en"
        for language in LANGUAGES:
            action = QAction(language.native_name, self)
            action.setCheckable(True)
            action.setChecked(language.code == active_language)
            action.triggered.connect(lambda checked=False, code=language.code: self._change_language(code))
            menu_language.addAction(action)
            self.language_actions.append(action)
        menu_help = self.menuBar().addMenu("&Help")
        menu_help.addAction(self.action_about)

    def _change_language(self, code: str) -> None:
        try:
            manager = language_manager()
        except RuntimeError:
            return
        manager.set_language(code)
        for action, language in zip(self.language_actions, LANGUAGES):
            action.setChecked(language.code == code)
        self.log(f"Interface language: {next(item.native_name for item in LANGUAGES if item.code == code)}")

    def _build_toolbar(self) -> None:
        toolbar = QToolBar("Main tools", self)
        toolbar.setMovable(False)
        toolbar.addActions([self.action_new, self.action_open, self.action_extract, self.action_inject, self.action_up])
        toolbar.addSeparator()
        toolbar.addActions([self.action_convert, self.action_verify])
        self.addToolBar(toolbar)

    def _build_layout(self) -> None:
        workspace = QWidget()
        workspace_layout = QVBoxLayout(workspace)
        workspace_layout.setContentsMargins(0, 0, 0, 0)
        workspace_layout.setSpacing(4)
        header = QFrame()
        header.setObjectName("workspaceHeader")
        header_layout = QHBoxLayout(header)
        header_layout.setContentsMargins(18, 12, 18, 12)
        title_box = QVBoxLayout()
        title = QLabel("DiskForge Workspace")
        title.setObjectName("workspaceTitle")
        subtitle = QLabel("Inspect, shape, validate, and distribute disk images with confidence.")
        subtitle.setObjectName("workspaceSubtitle")
        title_box.addWidget(title)
        title_box.addWidget(subtitle)
        header_layout.addLayout(title_box)
        header_layout.addStretch()
        badge = QLabel("IMAGE STUDIO")
        badge.setObjectName("workspaceBadge")
        header_layout.addWidget(badge)
        workspace_layout.addWidget(header)
        splitter = QSplitter(Qt.Orientation.Horizontal)
        self.tree = QTreeWidget()
        self.tree.setHeaderLabels(["Image explorer"])
        self.tree.itemSelectionChanged.connect(self._tree_selected)
        self.tree.setMinimumWidth(245)
        splitter.addWidget(self.tree)
        right = QWidget()
        right_layout = QVBoxLayout(right)
        path_row = QHBoxLayout()
        self.path_label = QLabel("No image open")
        self.path_label.setTextInteractionFlags(Qt.TextInteractionFlag.TextSelectableByMouse)
        path_row.addWidget(QLabel("<b>Location</b>"))
        path_row.addWidget(self.path_label, 1)
        up_button = QPushButton("Up")
        up_button.clicked.connect(self.go_up)
        path_row.addWidget(up_button)
        right_layout.addLayout(path_row)
        self.table = ImageEntryTable(0, 6)
        self.table.setHorizontalHeaderLabels(["Name", "Type", "Size", "Modified", "Attributes", "Path"])
        self.table.setSelectionBehavior(QAbstractItemView.SelectionBehavior.SelectRows)
        self.table.setSelectionMode(QAbstractItemView.SelectionMode.ExtendedSelection)
        self.table.setEditTriggers(QAbstractItemView.EditTrigger.NoEditTriggers)
        self.table.setSortingEnabled(True)
        self.table.setAlternatingRowColors(True)
        self.table.setShowGrid(False)
        self.table.horizontalHeader().setSectionResizeMode(0, QHeaderView.ResizeMode.Stretch)
        self.table.horizontalHeader().setSectionResizeMode(5, QHeaderView.ResizeMode.Stretch)
        self.table.setColumnWidth(1, 100)
        self.table.setColumnWidth(2, 100)
        self.table.setColumnWidth(3, 160)
        self.table.setColumnWidth(4, 110)
        self.table.itemDoubleClicked.connect(self._table_open)
        self.table.local_paths_dropped.connect(self._inject_dropped_paths)
        self.table.entry_drag_requested.connect(self.drag_out_selected)
        self.table.itemSelectionChanged.connect(self._update_action_state)
        self.table.setToolTip("Drop local files or folders here to inject them into a writable FAT image. Drag selected entries out to copy them to another application.")
        self.icon_view = ImageEntryList()
        self.icon_view.setViewMode(ImageEntryList.ViewMode.IconMode)
        self.icon_view.setResizeMode(ImageEntryList.ResizeMode.Adjust)
        self.icon_view.setMovement(ImageEntryList.Movement.Static)
        self.icon_view.setWrapping(True)
        self.icon_view.setSpacing(12)
        self.icon_view.setIconSize(QSize(52, 52))
        self.icon_view.local_paths_dropped.connect(self._inject_dropped_paths)
        self.icon_view.entry_drag_requested.connect(self.drag_out_selected)
        self.icon_view.itemDoubleClicked.connect(self._icon_open)
        self.icon_view.itemSelectionChanged.connect(self._update_action_state)
        self.icon_view.setToolTip("Drop local files or folders here to inject them into a writable FAT image. Drag selected entries out to copy them to another application.")
        self.view_stack = QStackedWidget()
        self.view_stack.addWidget(self.table)
        self.view_stack.addWidget(self.icon_view)
        right_layout.addWidget(self.view_stack, 1)
        page_row = QHBoxLayout()
        self.directory_page_label = QLabel()
        self.load_more_button = QPushButton("Load more")
        self.load_more_button.clicked.connect(self.load_more_entries)
        page_row.addWidget(self.directory_page_label, 1)
        page_row.addWidget(self.load_more_button)
        right_layout.addLayout(page_row)
        splitter.addWidget(right)
        splitter.setStretchFactor(1, 1)
        dock_tabs = QTabWidget()
        self.info_view = QTextBrowser()
        self.info_view.setOpenExternalLinks(True)
        self.log_view = QPlainTextEdit()
        self.log_view.setReadOnly(True)
        self.task_view = QTreeWidget()
        self.task_view.setHeaderLabels(["Status", "Task", "Detail"])
        self.task_view.setRootIsDecorated(False)
        clear_tasks = QPushButton("Clear completed tasks")
        clear_tasks.clicked.connect(self._clear_completed_tasks)
        tasks_panel = QWidget()
        tasks_layout = QVBoxLayout(tasks_panel)
        tasks_layout.setContentsMargins(0, 0, 0, 0)
        tasks_layout.addWidget(self.task_view)
        tasks_layout.addWidget(clear_tasks)
        dock_tabs.addTab(self.info_view, "Image information")
        dock_tabs.addTab(self.log_view, "Activity")
        dock_tabs.addTab(tasks_panel, "Tasks")
        dock = QWidget()
        dock_layout = QVBoxLayout(dock)
        dock_layout.setContentsMargins(0, 0, 0, 0)
        dock_layout.addWidget(dock_tabs)
        splitter.addWidget(dock)
        splitter.setSizes([245, 700, 335])
        workspace_layout.addWidget(splitter, 1)
        self.setCentralWidget(workspace)

    def _build_statusbar(self) -> None:
        status = QStatusBar()
        self.setStatusBar(status)
        self.status_label = QLabel("Ready")
        self.progress = QProgressBar()
        self.progress.setRange(0, 100)
        self.progress.setValue(0)
        self.progress.setMaximumWidth(230)
        self.cancel_button = QPushButton("Cancel")
        self.cancel_button.setEnabled(False)
        self.cancel_button.clicked.connect(self.cancel_operation)
        status.addWidget(self.status_label, 1)
        status.addPermanentWidget(self.progress)
        status.addPermanentWidget(self.cancel_button)

    def _restore_state(self) -> None:
        geometry = self.settings.value("geometry")
        if geometry:
            self.restoreGeometry(geometry)
        self.set_view_mode(str(self.settings.value("directory_view", "details")))

    def closeEvent(self, event) -> None:  # type: ignore[no-untyped-def]
        self.settings.setValue("geometry", self.saveGeometry())
        self._close_fs()
        if self.current_mount_session:
            try:
                ImageMountManager().unmount(self.current_mount_session)
            except Exception:
                pass
            self.current_mount_session = None
        for directory in self._preview_directories:
            shutil.rmtree(directory, ignore_errors=True)
        super().closeEvent(event)

    def _recent_paths(self) -> list[Path]:
        raw = self.settings.value("recent_images", [])
        values = raw if isinstance(raw, list) else [raw] if raw else []
        return [Path(str(value)) for value in values if Path(str(value)).is_file()]

    def _remember_recent(self, path: Path) -> None:
        paths = [path, *(candidate for candidate in self._recent_paths() if candidate != path)]
        self.settings.setValue("recent_images", [str(candidate) for candidate in paths[:12]])

    def _populate_recent_menu(self) -> None:
        self.recent_menu.clear()
        paths = self._recent_paths()
        if not paths:
            empty = self.recent_menu.addAction("No recent images")
            empty.setEnabled(False)
            return
        for path in paths:
            action = self.recent_menu.addAction(path.name)
            action.setToolTip(str(path))
            action.triggered.connect(lambda checked=False, value=path: self._open_path(value))
        self.recent_menu.addSeparator()
        clear = self.recent_menu.addAction("Clear recent images")
        clear.triggered.connect(lambda: self.settings.remove("recent_images"))

    def _update_action_state(self) -> None:
        open_image = self.current_path is not None
        entries = bool(self._selected_paths())
        fs_writable = isinstance(self.current_fs, FatImageFilesystem) and not getattr(self.current_fs, "read_only", False)
        selected_file = next((entry for entry in self.current_entries if entry.path in self._selected_paths() and not entry.is_dir), None)
        for action in [self.action_close, self.action_convert, self.action_resize, self.action_compare,
                       self.action_verify, self.action_partitions, self.action_boot, self.action_comment,
                       self.action_bundle, self.action_sfx, self.action_trim_zero_tail, self.action_iso_boot,
                       self.action_replace_iso, self.action_edit_iso]:
            action.setEnabled(open_image)
        fat_source = open_image and isinstance(self.current_fs, FatImageFilesystem)
        self.action_wrap_mbr.setEnabled(fat_source)
        self.action_prepare_deployment.setEnabled(fat_source)
        iso_open = open_image and self.current_info is not None and (self.current_info.image_format == ImageFormat.ISO or self.current_info.filesystem == FileSystemType.ISO9660)
        self.action_iso_boot.setEnabled(iso_open)
        self.action_replace_iso.setEnabled(iso_open and selected_file is not None and len(self._selected_paths()) == 1)
        self.action_edit_iso.setEnabled(iso_open)
        fixed_fat_vhd = fat_source and self.current_info is not None and self.current_info.image_format == ImageFormat.VHD and any(
            note.startswith("Fixed VHD footer validated") for note in self.current_info.notes
        )
        self.action_editable_vhd.setEnabled(fixed_fat_vhd)
        self.action_dynamic_vhd.setEnabled(fat_source)
        self.action_convert_dmg.setEnabled(open_image and self.current_info is not None and self.current_info.image_format == ImageFormat.DMG)
        self.action_mount.setEnabled(open_image and self.current_mount_session is None)
        self.action_legacy_zip.setEnabled(open_image and self.current_info is not None and self.current_info.image_format not in {ImageFormat.IMZ, ImageFormat.WLZ})
        self.action_unmount.setEnabled(self.current_mount_session is not None)
        self.action_extract.setEnabled(open_image and entries and self.current_fs is not None)
        self.action_preview.setEnabled(open_image and self.current_fs is not None and selected_file is not None and len(self._selected_paths()) == 1)
        self.action_inject.setEnabled(fs_writable)
        controlled_filesystem = open_image and self.current_info is not None and self.current_info.filesystem in {
            FileSystemType.NTFS, FileSystemType.EXT, FileSystemType.HFS,
        }
        self.action_controlled_inject.setEnabled(controlled_filesystem)
        self.action_delete.setEnabled(fs_writable and entries)
        self.action_properties.setEnabled(fs_writable and entries)
        self.action_rename.setEnabled(fs_writable and len(self._selected_paths()) == 1)
        self.action_attributes.setEnabled(fs_writable and len(self._selected_paths()) == 1)
        self.action_label.setEnabled(fs_writable)
        self.action_export.setEnabled(open_image and self.current_fs is not None)
        self.action_print.setEnabled(open_image and self.current_fs is not None)
        self.action_defragment.setEnabled(fs_writable)
        self.action_up.setEnabled(open_image and self.current_directory != "/")
        self.table.set_local_path_drop_enabled(fs_writable)
        self.table.set_entry_drag_enabled(open_image and entries and self.current_fs is not None)
        self.icon_view.set_local_path_drop_enabled(fs_writable)
        self.icon_view.set_entry_drag_enabled(open_image and entries and self.current_fs is not None)

    def log(self, message: str) -> None:
        stamp = datetime.now().strftime("%H:%M:%S")
        self.log_view.appendPlainText(f"[{stamp}] {message}")

    def _task_item(self, worker: FunctionWorker, title: str) -> QTreeWidgetItem:
        item = QTreeWidgetItem(["Queued", title, "Waiting to start"])
        self.task_view.addTopLevelItem(item)
        self._task_items[id(worker)] = item
        self.task_view.scrollToItem(item)
        return item

    def _set_task_state(self, worker: FunctionWorker, status: str, detail: str) -> None:
        item = self._task_items.get(id(worker))
        if item:
            item.setText(0, status)
            item.setText(2, detail)

    def _clear_completed_tasks(self) -> None:
        completed = {"Completed", "Failed", "Cancelled"}
        for index in reversed(range(self.task_view.topLevelItemCount())):
            item = self.task_view.topLevelItem(index)
            if item.text(0) in completed:
                self.task_view.takeTopLevelItem(index)
        self._task_items = {key: item for key, item in self._task_items.items() if item.treeWidget() is self.task_view}

    def _run_worker(self, title: str, function: Callable, *args, on_result: Callable | None = None, **kwargs) -> None:  # type: ignore[no-untyped-def]
        if self.current_worker:
            QMessageBox.information(self, "Operation in progress", "Wait for the current operation to finish or cancel it.")
            return
        worker = FunctionWorker(title, function, *args, **kwargs)
        self.current_worker = worker
        self._task_item(worker, title)
        worker.signals.started.connect(lambda text, value=worker: self._worker_started(text, value))
        worker.signals.progress.connect(lambda event, value=worker: self._worker_progress(event, value))
        worker.signals.result.connect(lambda result, value=worker: self._worker_result_for(value, result, on_result))
        worker.signals.error.connect(lambda message, details, value=worker: self._worker_error_for(value, message, details))
        worker.signals.finished.connect(lambda value=worker: self._worker_finished(value))
        self.thread_pool.start(worker)

    def _worker_started(self, title: str, worker: FunctionWorker | None = None) -> None:
        self.status_label.setText(title)
        self.progress.setValue(0)
        self.cancel_button.setEnabled(True)
        if worker:
            self._set_task_state(worker, "Running", title)
        self.log(title)

    def _worker_progress(self, event: Progress, worker: FunctionWorker | None = None) -> None:
        self.progress.setValue(event.percent)
        detail = f"{event.message} ({event.percent}%)"
        self.status_label.setText(detail)
        if worker:
            self._set_task_state(worker, "Running", detail)

    def _worker_result_for(self, worker: FunctionWorker, value: object, on_result: Callable | None) -> None:
        self._set_task_state(worker, "Completed", "Completed successfully")
        if on_result:
            on_result(value)
        else:
            self._worker_result(value)

    def _worker_error_for(self, worker: FunctionWorker, message: str, details: str) -> None:
        status = "Cancelled" if "cancel" in message.lower() else "Failed"
        self._set_task_state(worker, status, message)
        self._worker_error(message, details)

    def _worker_result(self, value: object) -> None:
        self.log(f"Completed: {value}")

    def _worker_error(self, message: str, details: str) -> None:
        self.log(f"Failed: {message}")
        QMessageBox.critical(self, "Operation failed", f"{message}\n\nSee Activity for details.")
        self.log(details)

    def _worker_finished(self, worker: FunctionWorker | None = None) -> None:
        self.progress.setValue(0)
        self.status_label.setText("Ready")
        self.cancel_button.setEnabled(False)
        if worker is None or self.current_worker is worker:
            self.current_worker = None
        self._update_action_state()

    def cancel_operation(self) -> None:
        if self.current_worker:
            self.current_worker.cancel()
            self._set_task_state(self.current_worker, "Cancelling", "Waiting for the current block to stop")
            self.status_label.setText("Cancelling after the current block…")

    def new_image(self) -> None:
        dialog = NewImageDialog(self)
        if dialog.exec() != QDialog.DialogCode.Accepted:
            return
        kind = dialog.kind.currentData()
        if kind == "hfs":
            creator = HfsImageCreator()
            report = creator.capability_report()
            if not report.available:
                QMessageBox.information(self, "Optional backend unavailable", report.reason)
                return
            output, _ = QFileDialog.getSaveFileName(
                self, "Create classic HFS image", "untitled.hfs", "Classic HFS image (*.hfs);;All files (*)",
            )
            if not output:
                return
            target = Path(output)
            size_bytes = dialog.hfs_size.value() * 1024

            def create_hfs(progress=None, token=None):
                return creator.create(target, size_bytes, dialog.label.text(), progress=progress, token=token)

            self._run_worker(
                "Creating verified classic HFS image", create_hfs,
                on_result=lambda result: self._open_path(result.destination),
            )
            return
        if kind == "iso":
            source = Path(dialog.source.text())
            if not source.is_dir():
                QMessageBox.warning(self, "Source directory required", "Choose a valid directory to create the ISO image.")
                return
            output, _ = QFileDialog.getSaveFileName(self, "Create ISO", str(source.with_suffix(".iso")), "ISO image (*.iso)")
            if not output:
                return
            boot_image_text = dialog.boot_image.text().strip()
            boot_image = Path(boot_image_text) if boot_image_text else None
            if boot_image is not None and not boot_image.is_file():
                QMessageBox.warning(self, "Boot image unavailable", "Choose a valid local boot image or leave the field empty.")
                return
            boot_media = str(dialog.boot_media.currentData())
            boot_info_table = dialog.boot_info_table.isChecked()
            rock_ridge = dialog.rock_ridge.isChecked()
            udf = dialog.udf.isChecked()
            def create_iso(progress=None, token=None):
                return create_iso_from_directory(
                    source, Path(output), dialog.label.text(), boot_image=boot_image,
                    boot_media=boot_media, boot_info_table=boot_info_table,
                    rock_ridge=rock_ridge, udf=udf,
                )
            self._run_worker("Creating bootable ISO image" if boot_image else "Creating ISO image", create_iso, on_result=lambda result: self._open_path(Path(result)))
            return
        is_legacy_floppy = kind == "legacy_floppy"
        legacy_format = ImageFormat(str(dialog.legacy_format.currentData())) if is_legacy_floppy else None
        suffix = f".{legacy_format.value}" if legacy_format is not None else ".img"
        image_filter = "Legacy floppy image (*.ima *.img)" if is_legacy_floppy else "Disk image (*.img *.ima)"
        output, _ = QFileDialog.getSaveFileName(self, "Create legacy floppy image" if is_legacy_floppy else "Create image", f"untitled{suffix}", image_filter)
        if not output:
            return
        target = Path(output)
        size = dialog.size.value() * 1024 * 1024
        if is_legacy_floppy:
            assert legacy_format is not None
            if dialog.legacy_custom.isChecked():
                geometry = LegacyFloppyGeometry(
                    dialog.legacy_cylinders.value(), dialog.legacy_heads.value(), dialog.legacy_sectors.value(),
                    int(dialog.legacy_sector_size.currentData()),
                )
                def create_legacy(progress=None, token=None):
                    return create_legacy_fat_floppy(target, geometry, image_format=legacy_format, label=dialog.label.text())
                title = "Creating custom legacy FAT floppy image"
            else:
                profile_id = str(dialog.legacy_profile.currentData())
                def create_legacy(progress=None, token=None):
                    return create_legacy_fat_floppy_profile(target, profile_id, image_format=legacy_format, label=dialog.label.text())
                title = "Creating legacy FAT floppy image"
            self._run_worker(title, create_legacy, on_result=lambda result: self._open_path(Path(result)))
        elif kind == "dmf":
            target = target.with_suffix(".dmf") if target.suffix.lower() not in {".dmf", ".img", ".ima"} else target
            def create_dmf(progress=None, token=None):
                return create_dmf_image(target, dialog.label.text())
            self._run_worker("Creating DMF layout image", create_dmf, on_result=lambda result: self._open_path(Path(result)))
        elif kind == "fat_layout":
            template = Path(dialog.source.text().strip())
            if not template.is_file():
                QMessageBox.warning(self, "FAT template required", "Choose a valid FAT image template before creating a layout-based image.")
                return
            try:
                layout = FatImageLayout.from_image(template)
            except (DiskForgeError, OSError) as exc:
                QMessageBox.warning(self, "Invalid FAT template", str(exc))
                return
            def create_from_layout(progress=None, token=None):
                return create_fat_image_from_layout(target, layout, label=dialog.label.text())
            self._run_worker("Creating FAT image from template layout", create_from_layout,
                             on_result=lambda result: self._open_path(Path(result)))
        elif kind == "raw":
            def create_raw(progress=None, token=None):
                target.parent.mkdir(parents=True, exist_ok=True)
                with target.open("wb") as handle:
                    handle.truncate(size)
                return target
            self._run_worker("Creating raw image", create_raw, on_result=lambda result: self._open_path(Path(result)))
        else:
            filesystem = FileSystemType(dialog.fat.currentText())
            def create(progress=None, token=None):
                return create_fat_image(target, size, filesystem, dialog.label.text())
            self._run_worker("Formatting FAT image", create, on_result=lambda result: self._open_path(Path(result)))

    def open_image(self) -> None:
        start = str(self.settings.value("last_directory", ""))
        path, _ = QFileDialog.getOpenFileName(self, "Open disk image", start, IMAGE_FILTER)
        if path:
            self._open_path(Path(path))

    def create_editable_vhd_copy(self) -> None:
        """Create a separately stored fixed-VHD FAT copy before enabling edits."""
        if not self.current_path or not self.action_editable_vhd.isEnabled():
            return
        source = self.current_path
        default = source.with_name(f"{source.stem}-editable.vhd")
        output, _ = QFileDialog.getSaveFileName(self, "Create editable fixed VHD copy", str(default), "Fixed VHD (*.vhd)")
        if not output:
            return
        destination = Path(output)
        if destination == source:
            QMessageBox.warning(self, "Separate output required", "Choose a different output file; the original fixed VHD is kept read-only.")
            return
        def create_copy(progress=None, token=None):
            return create_editable_fixed_vhd_copy(source, destination, progress=progress, token=token)
        self._run_worker(
            "Creating editable fixed VHD copy", create_copy,
            on_result=lambda result: self._open_path(Path(result.destination), editable_fixed_vhd=True),
        )

    def create_dynamic_vhd(self) -> None:
        """Export the current FAT work image as a separately validated dynamic VHD."""
        if not self.current_path or not isinstance(self.current_fs, FatImageFilesystem):
            return
        source = self.current_path
        converter = QemuImgConverter(self.settings.value("qemu_img_path", "") or None)
        report = converter.capability_report()
        if not report.available:
            QMessageBox.information(self, "Dynamic VHD adapter unavailable", report.reason)
            return
        default = source.with_suffix(".dynamic.vhd")
        output, _ = QFileDialog.getSaveFileName(self, "Create dynamic VHD from FAT work image", str(default), "VHD image (*.vhd)")
        if not output:
            return
        destination = Path(output)
        if destination.resolve() == source.resolve():
            QMessageBox.warning(self, "Separate output required", "Choose a different output file; the FAT work image remains unchanged.")
            return
        self._run_worker("Creating verified dynamic VHD", create_dynamic_vhd_from_raw, source, destination, converter,
                         on_result=lambda result: self._open_path(result.destination))

    def convert_dmg_image(self) -> None:
        """Convert a DMG through an explicitly configured read-only adapter."""
        if not self.current_path or not self.current_info or self.current_info.image_format != ImageFormat.DMG:
            return
        converter = Dmg2ImgConverter(self.settings.value("dmg2img_path", "") or None)
        report = converter.capability_report()
        if not report.available:
            QMessageBox.warning(self, "DMG adapter unavailable", report.reason)
            return
        source = self.current_path
        output, _ = QFileDialog.getSaveFileName(self, "Convert DMG to raw image", str(source.with_suffix(".img")), "Raw image (*.img *.raw)")
        if not output:
            return
        destination = Path(output)
        def convert_dmg(progress=None, token=None):
            return converter.convert(source, destination, token=token)
        self._run_worker("Converting DMG to raw image", convert_dmg, on_result=lambda result: self._open_path(Path(result)))

    def mount_current_image(self) -> None:
        """Ask the OS backend to attach the current image read-only only."""
        if not self.current_path or self.current_mount_session is not None:
            return
        source = self.current_path
        manager = ImageMountManager()
        report = manager.capability_report()
        if not report.available:
            QMessageBox.information(self, "Read-only mount unavailable", report.reason)
            return
        self._run_worker("Mounting image read-only", manager.mount, source, on_result=self._mounted_image)

    def _mounted_image(self, session: ImageMountSession) -> None:
        self.current_mount_session = session
        location = str(session.mount_point) if session.mount_point else session.device or "system-managed mount"
        QMessageBox.information(self, "Image mounted read-only", f"The image is mounted read-only at:\n{location}")
        self._update_action_state()

    def unmount_current_image(self) -> None:
        if not self.current_mount_session:
            return
        session = self.current_mount_session
        self._run_worker("Unmounting image", ImageMountManager().unmount, session, on_result=lambda _result: self._unmounted_image())

    def _unmounted_image(self) -> None:
        self.current_mount_session = None
        QMessageBox.information(self, "Image unmounted", "The DiskForge read-only mount session has been released.")
        self._update_action_state()

    def replace_iso_file(self) -> None:
        """Create a verified ISO copy with one selected equal-length file replaced."""
        if not self.current_path or not isinstance(self.current_fs, IsoImageFilesystem):
            return
        selected = next((entry for entry in self.current_entries
                         if entry.path in self._selected_paths() and not entry.is_dir), None)
        if selected is None:
            QMessageBox.information(self, "Select ISO file", "Select exactly one regular ISO file to replace safely.")
            return
        replacement, _ = QFileDialog.getOpenFileName(self, "Select equal-size replacement file", "", "All files (*)")
        if not replacement:
            return
        source_iso = self.current_path
        source_file = Path(replacement)
        default = source_iso.with_name(f"{source_iso.stem}-replaced.iso")
        output, _ = QFileDialog.getSaveFileName(self, "Save replaced ISO copy", str(default), "ISO image (*.iso)")
        if not output:
            return
        destination = Path(output)
        if destination.resolve() == source_iso.resolve():
            QMessageBox.warning(self, "Separate output required", "The source ISO remains unchanged; choose a different output file.")
            return
        def replace(progress=None, token=None):
            return replace_iso_file_safely(source_iso, selected.path, source_file, destination)
        self._run_worker("Safely replacing ISO file into a new image", replace,
                         on_result=lambda result: self._open_path(Path(result.destination)))

    def edit_standard_iso(self) -> None:
        """Rebuild a supported ISO after one explicit content edit."""
        if not self.current_path or not isinstance(self.current_fs, IsoImageFilesystem):
            return
        choices = [
            "Add local file…", "Add local folder…", "Delete selected ISO entries", "Create ISO directory…",
        ]
        operation, accepted = QInputDialog.getItem(self, "Edit ISO content safely", "Operation", choices, 0, False)
        if not accepted:
            return
        additions: list[Path] = []
        deletions: list[str] = []
        directories: list[str] = []
        target_directory = "/"
        selected_entries = [entry for entry in self.current_entries if entry.path in self._selected_paths()]
        selected_directory = next((entry for entry in selected_entries if entry.is_dir), None)
        if selected_directory is not None:
            target_directory = selected_directory.path
        if operation == "Add local file…":
            filename, _ = QFileDialog.getOpenFileName(self, "Select local file to add", "", "All files (*)")
            if not filename:
                return
            additions = [Path(filename)]
        elif operation == "Add local folder…":
            directory = QFileDialog.getExistingDirectory(self, "Select local folder to add")
            if not directory:
                return
            additions = [Path(directory)]
        elif operation == "Delete selected ISO entries":
            deletions = [entry.path for entry in selected_entries]
            if not deletions:
                QMessageBox.information(self, "Select ISO entries", "Select one or more ISO files or directories to delete.")
                return
        else:
            directory, accepted = QInputDialog.getText(self, "Create ISO directory", "ISO directory path")
            if not accepted or not directory.strip():
                return
            directories = [directory]
        source_iso = self.current_path
        default = source_iso.with_name(f"{source_iso.stem}-edited.iso")
        output, _ = QFileDialog.getSaveFileName(self, "Save rebuilt ISO image", str(default), "ISO image (*.iso)")
        if not output:
            return
        destination = Path(output)
        if destination.resolve() == source_iso.resolve():
            QMessageBox.warning(self, "Separate output required", "The source ISO remains unchanged; choose a different output file.")
            return
        def rebuild(progress=None, token=None):
            return rebuild_iso_with_changes(
                source_iso, destination, additions=additions, delete_paths=deletions,
                create_directories=directories, target_directory=target_directory,
                progress=progress, token=token,
            )
        self._run_worker("Rebuilding ISO into a new image", rebuild,
                         on_result=lambda result: self._open_path(Path(result.destination)))

    def _open_path(self, path: Path, *, editable_fixed_vhd: bool = False,
                   partition_index: int | None = None) -> None:
        try:
            self._close_fs()
            self._editable_fixed_vhd = False
            self.current_partition_index = partition_index
            self.current_path = path
            converter = QemuImgConverter(self.settings.value("qemu_img_path", "") or None)
            self.current_info = inspect_image(path, converter)
            browse_path, browse_info = path, self.current_info
            direct_editable_vhd = editable_fixed_vhd and self.current_info.image_format == ImageFormat.VHD
            if direct_editable_vhd:
                validate_fixed_vhd_fat(path)
                self._editable_fixed_vhd = True
                self.log(f"Opened validated editable fixed-VHD copy for {path.name}")
            elif self.current_info.image_format in {ImageFormat.VHD, ImageFormat.VHDX, ImageFormat.VMDK, ImageFormat.QCOW2,
                                                    ImageFormat.IMZ, ImageFormat.WLZ}:
                self.current_browse_session = materialize_browsable_image(path, converter=converter)
                browse_path = self.current_browse_session.image
                browse_info = inspect_image(browse_path)
                self.log(f"Opened read-only temporary browse session for {path.name}")
            self.current_directory = "/"
            if partition_index is not None:
                self.current_fs = open_partition_filesystem(browse_path, partition_index, writable=False)
            elif browse_info.filesystem in {FileSystemType.FAT12, FileSystemType.FAT16, FileSystemType.FAT32}:
                self.current_fs = FatImageFilesystem(browse_path, read_only=self.current_browse_session is not None)
            elif browse_info.filesystem == FileSystemType.ISO9660 or browse_info.image_format == ImageFormat.ISO:
                self.current_fs = IsoImageFilesystem(browse_path)
            elif browse_info.filesystem in {FileSystemType.NTFS, FileSystemType.EXT, FileSystemType.HFS, FileSystemType.HFS_PLUS}:
                self.current_fs = SleuthKitImageFilesystem(browse_path, browse_info.filesystem)
            else:
                self.current_fs = None
            self.settings.setValue("last_directory", str(path.parent))
            self._remember_recent(path)
            self._populate_tree()
            self._populate_table("/")
            self._show_info()
            self.setWindowTitle(f"DiskForge — {path.name}")
            self.log(f"Opened {path}")
        except Exception as exc:
            self.current_path = None
            self.current_info = None
            self._close_fs()
            QMessageBox.critical(self, "Cannot open image", str(exc))
        self._update_action_state()

    def _close_fs(self) -> None:
        if self.current_fs:
            try:
                self.current_fs.close()
            except Exception:
                pass
        self.current_fs = None
        if self.current_browse_session:
            self.current_browse_session.close()
            self.current_browse_session = None

    def close_image(self) -> None:
        self._close_fs()
        self.current_path, self.current_info, self.current_entries = None, None, []
        self.current_partition_index = None
        self.current_directory = "/"
        self.tree.clear()
        self.table.setRowCount(0)
        self.info_view.clear()
        self.path_label.setText("No image open")
        self.setWindowTitle("DiskForge — Disk Image Studio")
        self._update_action_state()

    def _populate_tree(self) -> None:
        self.tree.clear()
        if not self.current_path:
            return
        root = QTreeWidgetItem([self.current_path.name])
        root.setData(0, Qt.ItemDataRole.UserRole, "/")
        self.tree.addTopLevelItem(root)
        root.setExpanded(True)
        if self.current_fs:
            self._add_tree_children(root, "/", depth=0)
        self.tree.setCurrentItem(root)

    def _add_tree_children(self, parent: QTreeWidgetItem, path: str, depth: int) -> None:
        if not self.current_fs or depth > 8:
            return
        try:
            for entry in self.current_fs.list_entries(path):
                if entry.is_dir:
                    child = QTreeWidgetItem([entry.name])
                    child.setData(0, Qt.ItemDataRole.UserRole, entry.path)
                    parent.addChild(child)
                    self._add_tree_children(child, entry.path, depth + 1)
        except Exception as exc:
            self.log(f"Unable to populate tree {path}: {exc}")

    def _tree_selected(self) -> None:
        item = self.tree.currentItem()
        if item:
            target = item.data(0, Qt.ItemDataRole.UserRole)
            if target:
                self._populate_table(str(target))

    def _render_directory_entries(self, entries: Sequence[ImageEntry], *, reset: bool) -> None:
        self.table.setSortingEnabled(False)
        if reset:
            self.table.setRowCount(0)
            self.icon_view.clear()
        start = self.table.rowCount()
        self.table.setRowCount(start + len(entries))
        for row, entry in enumerate(entries, start):
            icon_kind = QStyle.StandardPixmap.SP_DirIcon if entry.is_dir else QStyle.StandardPixmap.SP_FileIcon
            icon_item = QListWidgetItem(self.style().standardIcon(icon_kind), entry.name)
            icon_item.setData(Qt.ItemDataRole.UserRole, entry.path)
            icon_item.setData(Qt.ItemDataRole.UserRole + 1, entry.is_dir)
            icon_item.setToolTip(entry.path)
            self.icon_view.addItem(icon_item)
            name = QTableWidgetItem(entry.name)
            name.setData(Qt.ItemDataRole.UserRole, entry.path)
            name.setToolTip(entry.path)
            self.table.setItem(row, 0, name)
            self.table.setItem(row, 1, QTableWidgetItem("Folder" if entry.is_dir else "File"))
            self.table.setItem(row, 2, QTableWidgetItem("—" if entry.is_dir else human_bytes(entry.size)))
            self.table.setItem(row, 3, QTableWidgetItem(entry.modified.strftime("%Y-%m-%d %H:%M:%S") if entry.modified else ""))
            self.table.setItem(row, 4, QTableWidgetItem(entry.attributes))
            self.table.setItem(row, 5, QTableWidgetItem(entry.path))
        self.table.setSortingEnabled(True)

    def _update_directory_page_controls(self) -> None:
        shown = len(self.current_entries)
        total = self._directory_total
        self.directory_page_label.setText(f"Showing {shown} of {total} item(s)" if total else "")
        self.load_more_button.setVisible(total > self._directory_page_size)
        self.load_more_button.setEnabled(shown < total)
        self.load_more_button.setText("Load more" if shown < total else "All items loaded")

    def _load_directory_page(self, *, reset: bool) -> None:
        if not self.current_fs:
            return
        offset = 0 if reset else len(self.current_entries)
        try:
            page = self.current_fs.list_entries_page(
                self.current_directory, offset=offset, limit=self._directory_page_size,
                sort_by=self._directory_sort_by, ascending=self._directory_sort_ascending,
            )
            if reset:
                self.current_entries = []
            self.current_entries.extend(page.entries)
            self._directory_total = page.total
            self._render_directory_entries(page.entries, reset=reset)
            self._update_directory_page_controls()
        except Exception as exc:
            self.log(f"Unable to list {self.current_directory}: {exc}")

    def load_more_entries(self) -> None:
        if self.current_fs and len(self.current_entries) < self._directory_total:
            self._load_directory_page(reset=False)
            self._update_action_state()

    def _populate_table(self, path: str) -> None:
        self.current_directory = path
        self.path_label.setText(path)
        self.current_entries = []
        self._directory_total = 0
        if self.current_fs:
            self._load_directory_page(reset=True)
        elif self.current_path:
            self.icon_view.clear()
            item = QTableWidgetItem("Filesystem browsing is not available for this format. Inspect metadata, partitions, convert to RAW, or install qemu-img for virtual-disk conversion.")
            item.setFlags(Qt.ItemFlag.ItemIsEnabled)
            self.table.setRowCount(1)
            self.table.setSpan(0, 0, 1, 6)
            self.table.setItem(0, 0, item)
            self._update_directory_page_controls()
        self._update_action_state()

    def _selected_paths(self) -> list[str]:
        if self.view_stack.currentWidget() is self.icon_view:
            return [str(item.data(Qt.ItemDataRole.UserRole)) for item in self.icon_view.selectedItems() if item.data(Qt.ItemDataRole.UserRole)]
        paths: list[str] = []
        for index in self.table.selectionModel().selectedRows() if self.table.selectionModel() else []:
            item = self.table.item(index.row(), 0)
            if item and item.data(Qt.ItemDataRole.UserRole):
                paths.append(str(item.data(Qt.ItemDataRole.UserRole)))
        return paths

    def _table_open(self, item: QTableWidgetItem) -> None:
        self._open_entry(str(item.data(Qt.ItemDataRole.UserRole) or ""))

    def _icon_open(self, item: QListWidgetItem) -> None:
        self._open_entry(str(item.data(Qt.ItemDataRole.UserRole) or ""))

    def _open_entry(self, path: str) -> None:
        matching = next((entry for entry in self.current_entries if entry.path == path), None)
        if matching and matching.is_dir:
            self._populate_table(matching.path)
        elif matching:
            self.preview_selected()

    def set_view_mode(self, mode: str) -> None:
        normalized = "icons" if mode == "icons" else "details"
        selected = self._selected_paths() if hasattr(self, "view_stack") else []
        self.view_stack.setCurrentWidget(self.icon_view if normalized == "icons" else self.table)
        self.action_view_icons.setChecked(normalized == "icons")
        self.action_view_details.setChecked(normalized == "details")
        self.settings.setValue("directory_view", normalized)
        self._restore_selection(selected)
        self._update_action_state()

    def _restore_selection(self, paths: Sequence[str]) -> None:
        if self.view_stack.currentWidget() is self.icon_view:
            for index in range(self.icon_view.count()):
                item = self.icon_view.item(index)
                item.setSelected(str(item.data(Qt.ItemDataRole.UserRole) or "") in paths)
            return
        self.table.clearSelection()
        for row in range(self.table.rowCount()):
            item = self.table.item(row, 0)
            if item and str(item.data(Qt.ItemDataRole.UserRole) or "") in paths:
                self.table.selectRow(row)

    def go_up(self) -> None:
        if self.current_directory == "/":
            return
        parent = str(Path(self.current_directory).parent).replace("\\", "/")
        self._populate_table("/" if parent in {".", ""} else parent)

    def _show_info(self) -> None:
        if not self.current_info:
            self.info_view.clear()
            return
        info = self.current_info
        rows = [
            ("Path", str(info.path)), ("Format", info.image_format.value.upper()), ("Physical size", human_bytes(info.size)),
            ("Virtual size", human_bytes(info.virtual_size) if info.virtual_size else "—"),
            ("Filesystem", info.filesystem.value), ("Writable", "Yes" if info.writable else "No"),
            ("Sector size", f"{info.sector_size} bytes"),
        ]
        notes = "".join(f"<li>{note}</li>" for note in info.notes) or "<li>No additional format notes.</li>"
        table = "".join(f"<tr><th align='left'>{key}</th><td>{value}</td></tr>" for key, value in rows)
        self.info_view.setHtml(f"<h3>{info.path.name}</h3><table>{table}</table><h4>Inspection notes</h4><ul>{notes}</ul><p><i>DiskForge does not mount images automatically. Physical device writes remain separately protected.</i></p>")

    def _readonly_current_filesystem(self) -> ImageFilesystem:
        """Reopen the filesystem actually used by the active browse session.

        Virtual-disk sessions can browse a temporary RAW view even though the
        original file's outer format is VHD/VHDX/VMDK/QCOW2.  Re-detecting from
        the outer file routed these valid sessions to the NTFS/EXT-only adapter.
        """
        if self.current_fs is None or self.current_path is None:
            raise DiskForgeError("The current image has no browsable filesystem.")
        source = self.current_browse_session.image if self.current_browse_session else self.current_path
        if isinstance(self.current_fs, FatImageFilesystem):
            return FatImageFilesystem(source, read_only=True)
        if isinstance(self.current_fs, IsoImageFilesystem):
            return IsoImageFilesystem(source)
        if isinstance(self.current_fs, SleuthKitImageFilesystem):
            return SleuthKitImageFilesystem(source, self.current_fs.filesystem, offset=self.current_fs.offset)
        raise DiskForgeError("The current image format can be inspected but has no file-level browser.")

    def _choose_extraction_policy(self) -> ExtractionPolicy | None:
        dialog = QDialog(self)
        dialog.setWindowTitle("Extraction options")
        form = QFormLayout(dialog)
        layout = QComboBox()
        layout.addItem("Preserve image paths", ExtractionLayout.PRESERVE_PATHS)
        layout.addItem("Extract all files into one directory", ExtractionLayout.FLATTEN)
        layout.addItem("Ignore selected subdirectories", ExtractionLayout.IGNORE_SUBDIRECTORIES)
        conflict = QComboBox()
        conflict.addItem("Stop on existing file", ConflictPolicy.ERROR)
        conflict.addItem("Overwrite existing file", ConflictPolicy.OVERWRITE)
        conflict.addItem("Skip existing file", ConflictPolicy.SKIP)
        conflict.addItem("Rename conflicting file", ConflictPolicy.RENAME)
        form.addRow("Layout", layout)
        form.addRow("Existing files", conflict)
        buttons = QDialogButtonBox(QDialogButtonBox.StandardButton.Ok | QDialogButtonBox.StandardButton.Cancel)
        buttons.accepted.connect(dialog.accept)
        buttons.rejected.connect(dialog.reject)
        form.addRow(buttons)
        if dialog.exec() != QDialog.DialogCode.Accepted:
            return None
        return ExtractionPolicy(layout.currentData(), conflict.currentData())

    def extract_selected(self) -> None:
        if not self.current_fs:
            return
        paths = self._selected_paths()
        if not paths:
            QMessageBox.information(self, "Select files", "Select one or more files or folders to extract.")
            return
        policy = self._choose_extraction_policy()
        if policy is None:
            return
        destination = QFileDialog.getExistingDirectory(self, "Extract to directory")
        if not destination:
            return
        def job(progress=None, token=None):
            fs = self._readonly_current_filesystem()
            try:
                return fs.extract(paths, Path(destination), progress, token, policy)
            finally:
                fs.close()
        self._run_worker("Extracting selected items", job, on_result=lambda outputs: self.log(f"Extracted {len(outputs)} file(s) to {destination}"))

    def inject_files(self) -> None:
        if not isinstance(self.current_fs, FatImageFilesystem) or not self.current_path:
            return
        files, _ = QFileDialog.getOpenFileNames(self, "Inject files", str(self.settings.value("last_directory", "")), "All files (*)")
        if files:
            self._inject_local_paths([Path(value) for value in files], self.current_directory)

    def inject_files_safely(self) -> None:
        """Create and verify a separate NTFS, EXT or classic-HFS output; source is immutable."""
        if not self.current_path or self.current_info is None:
            return
        if self.current_info.filesystem == FileSystemType.NTFS:
            injector = NtfsFileInjector()
            output_suffix = ".ntfs"
        elif self.current_info.filesystem == FileSystemType.EXT:
            injector = ExtFileInjector()
            output_suffix = self.current_path.suffix or ".ext4"
        elif self.current_info.filesystem == FileSystemType.HFS:
            injector = HfsFileInjector()
            output_suffix = self.current_path.suffix or ".hfs"
        else:
            return
        report = injector.capability_report()
        if not report.available:
            QMessageBox.information(self, "Optional backend unavailable", report.reason)
            return
        notice = "This operation never changes the open image. It creates a separate output, accepts root-directory regular files only, refuses overwrite, and verifies every file after writing."
        if self.current_info.filesystem == FileSystemType.HFS:
            notice = "This operation never changes the open image. It creates a separate output, accepts root-directory regular files only, refuses overwrite, and verifies every file after writing. Classic HFS copies raw data forks only; HFS+ remains read-only."
        QMessageBox.information(self, "Safe NTFS/EXT/classic HFS injection", notice)
        files, _ = QFileDialog.getOpenFileNames(self, "Select regular local files", str(self.settings.value("last_directory", "")), "All files (*)")
        if not files:
            return
        source = self.current_path
        suggested = source.with_name(f"{source.stem}-injected{output_suffix}")
        destination, _ = QFileDialog.getSaveFileName(self, "Save verified output image", str(suggested), IMAGE_FILTER)
        if not destination:
            return
        target = Path(destination)
        def job(progress=None, token=None):
            return injector.inject(source, target, [Path(value) for value in files], progress=progress, token=token)
        def completed(result) -> None:
            self.log(f"Verified {self.current_info.filesystem.value} output created: {result.destination}")
            self._open_path(result.destination)
        self._run_worker("Creating verified NTFS/EXT/classic HFS output", job, on_result=completed)

    def _inject_dropped_paths(self, paths: list[Path], target_directory: str) -> None:
        """Inject local URLs accepted by the table's native drag-and-drop handler."""
        if not isinstance(self.current_fs, FatImageFilesystem) or not self.current_path:
            return
        readable = [path for path in paths if path.exists() and (path.is_file() or path.is_dir())]
        if not readable:
            return
        self._inject_local_paths(readable, target_directory)

    def _inject_local_paths(self, paths: Sequence[Path], target_directory: str) -> None:
        if not isinstance(self.current_fs, FatImageFilesystem) or not self.current_path:
            return
        source = self.current_path
        destination = target_directory or self.current_directory
        def job(progress=None, token=None):
            fs = FatImageFilesystem(source)
            try:
                return fs.inject(paths, destination, progress, token)
            finally:
                fs.close()
        self._run_worker("Injecting files", job, on_result=lambda values: self._after_fs_change(f"Injected {len(values)} item(s) into {destination}"))

    def preview_selected(self) -> None:
        """Extract one file to an isolated directory and inspect it without execution."""
        if not self.current_path or not self.current_fs:
            return
        paths = self._selected_paths()
        entry = next((candidate for candidate in self.current_entries if candidate.path in paths and not candidate.is_dir), None)
        if len(paths) != 1 or entry is None:
            return
        target = Path(tempfile.mkdtemp(prefix="diskforge-preview-"))
        self._preview_directories.append(target)
        self._active_preview_entry_path = entry.path
        def job(progress=None, token=None):
            fs = self._readonly_current_filesystem()
            try:
                outputs = fs.extract([entry.path], target, progress, token, ExtractionPolicy())
                if not outputs:
                    raise DiskForgeError("The selected file could not be extracted for preview.")
                return outputs[0]
            finally:
                fs.close()
        self._run_worker("Preparing file preview", job, on_result=self._show_preview)

    def _save_preview_back(self, entry_path: str, text: str, encoding: str) -> None:
        if not isinstance(self.current_fs, FatImageFilesystem) or getattr(self.current_fs, "read_only", False) or not self.current_path:
            QMessageBox.warning(self, "Save unavailable", "Only files in a writable FAT image can be saved back to the image.")
            return
        stage = Path(tempfile.mkdtemp(prefix="diskforge-edit-"))
        self._preview_directories.append(stage)
        local = stage / Path(entry_path).name
        try:
            local.write_text(text, encoding=encoding)
        except (OSError, UnicodeError) as exc:
            self._cleanup_preview(stage)
            QMessageBox.warning(self, "Save unavailable", str(exc))
            return
        image = self.current_path
        parent_directory = str(Path(entry_path).parent).replace("\\", "/")
        if parent_directory in {"", "."}:
            parent_directory = "/"
        def job(progress=None, token=None):
            filesystem = FatImageFilesystem(image)
            try:
                return filesystem.inject([local], parent_directory, progress, token)
            finally:
                filesystem.close()
        self._run_worker(
            "Saving edited text to FAT image", job,
            on_result=lambda values: (self._cleanup_preview(stage), self._after_fs_change(f"Saved edited file: {values[0]}")),
        )

    def _show_preview(self, path: Path) -> None:
        try:
            document = inspect_file_preview(path)
            entry_path = self._active_preview_entry_path
            can_save_back = isinstance(self.current_fs, FatImageFilesystem) and not getattr(self.current_fs, "read_only", False) and entry_path is not None
            callback = (lambda text, encoding: self._save_preview_back(entry_path, text, encoding)) if can_save_back and entry_path else None
            FilePreviewDialog(document, source_path=path, save_back=callback, parent=self).exec()
            self.log(f"Preview inspected: {path.name} ({document.kind})")
        except Exception as exc:
            QMessageBox.warning(self, "Preview unavailable", str(exc))
        finally:
            self._active_preview_entry_path = None
            self._cleanup_preview(path.parent)

    def _cleanup_preview(self, directory: Path) -> None:
        shutil.rmtree(directory, ignore_errors=True)
        if directory in self._preview_directories:
            self._preview_directories.remove(directory)

    def drag_out_selected(self) -> None:
        """Extract selected entries to a temporary directory and initiate a native copy drag."""
        if not self.current_path or not self.current_fs:
            return
        paths = self._selected_paths()
        if not paths:
            return
        temporary = Path(tempfile.mkdtemp(prefix="diskforge-drag-"))
        try:
            fs = self._readonly_current_filesystem()
            try:
                outputs = fs.extract(paths, temporary, policy=ExtractionPolicy(ExtractionLayout.PRESERVE_PATHS, ConflictPolicy.ERROR))
            finally:
                fs.close()
            if not outputs:
                return
            mime = QMimeData()
            mime.setUrls([QUrl.fromLocalFile(str(path)) for path in outputs])
            drag = QDrag(self.view_stack.currentWidget())
            drag.setMimeData(mime)
            self.status_label.setText(f"Dragging {len(outputs)} extracted file(s)…")
            action = drag.exec(Qt.DropAction.CopyAction)
            self.log(f"Drag-out {'completed' if action != Qt.DropAction.IgnoreAction else 'cancelled'} for {len(outputs)} file(s)")
        except Exception as exc:
            self.log(f"Unable to prepare dragged entries: {exc}")
            QMessageBox.warning(self, "Unable to drag entries", str(exc))
        finally:
            shutil.rmtree(temporary, ignore_errors=True)
            self.status_label.setText("Ready")

    def delete_selected(self) -> None:
        if not isinstance(self.current_fs, FatImageFilesystem) or not self.current_path:
            return
        paths = self._selected_paths()
        if not paths:
            return
        answer = QMessageBox.warning(self, "Delete image entries", f"Delete {len(paths)} selected item(s) from the image? This changes the image file.", QMessageBox.StandardButton.Delete | QMessageBox.StandardButton.Cancel, QMessageBox.StandardButton.Cancel)
        if answer != QMessageBox.StandardButton.Delete:
            return
        source = self.current_path
        def job(progress=None, token=None):
            fs = FatImageFilesystem(source)
            try:
                fs.delete(paths)
                return len(paths)
            finally:
                fs.close()
        self._run_worker("Deleting image entries", job, on_result=lambda count: self._after_fs_change(f"Deleted {count} item(s)"))

    def modify_timestamp(self) -> None:
        if not isinstance(self.current_fs, FatImageFilesystem) or not self.current_path:
            return
        paths = self._selected_paths()
        if not paths:
            return
        dialog = QDialog(self)
        dialog.setWindowTitle("Modify file timestamps")
        layout = QFormLayout(dialog)
        picker = QDateTimeEdit(QDateTime.currentDateTime())
        picker.setCalendarPopup(True)
        layout.addRow(f"Apply to {len(paths)} selected item(s)", picker)
        buttons = QDialogButtonBox(QDialogButtonBox.StandardButton.Apply | QDialogButtonBox.StandardButton.Cancel)
        buttons.accepted.connect(dialog.accept)
        buttons.rejected.connect(dialog.reject)
        layout.addRow(buttons)
        if dialog.exec() != QDialog.DialogCode.Accepted:
            return
        timestamp = picker.dateTime().toPython()
        source = self.current_path
        def job(progress=None, token=None):
            fs = FatImageFilesystem(source)
            try:
                for item_path in paths:
                    if token:
                        token.raise_if_cancelled()
                    fs.set_modified(item_path, timestamp)
                return len(paths)
            finally:
                fs.close()
        self._run_worker("Updating image timestamps", job, on_result=lambda count: self._after_fs_change(f"Updated timestamp for {count} item(s)"))

    def rename_selected(self) -> None:
        if not isinstance(self.current_fs, FatImageFilesystem) or not self.current_path:
            return
        paths = self._selected_paths()
        if len(paths) != 1:
            return
        current = next((entry for entry in self.current_entries if entry.path == paths[0]), None)
        value, accepted = QInputDialog.getText(self, "Rename image entry", "New name", text=current.name if current else "")
        if not accepted or not value.strip():
            return
        source = self.current_path
        self._run_worker("Renaming image entry", lambda progress=None, token=None: self._rename_in_image(source, paths[0], value), on_result=lambda path: self._after_fs_change(f"Renamed entry to {path}"))

    @staticmethod
    def _rename_in_image(source: Path, path: str, value: str) -> str:
        fs = FatImageFilesystem(source)
        try:
            return fs.rename(path, value)
        finally:
            fs.close()

    def edit_attributes(self) -> None:
        if not isinstance(self.current_fs, FatImageFilesystem) or not self.current_path:
            return
        paths = self._selected_paths()
        if len(paths) != 1:
            return
        entry = next((item for item in self.current_entries if item.path == paths[0]), None)
        dialog = QDialog(self)
        dialog.setWindowTitle("Edit DOS attributes")
        form = QFormLayout(dialog)
        boxes: dict[str, QCheckBox] = {}
        for key, label in (("read_only", "Read-only"), ("hidden", "Hidden"), ("system", "System"), ("archive", "Archive")):
            box = QCheckBox(label)
            box.setChecked(bool(entry and label[0] in entry.attributes))
            boxes[key] = box
            form.addRow(box)
        buttons = QDialogButtonBox(QDialogButtonBox.StandardButton.Apply | QDialogButtonBox.StandardButton.Cancel)
        buttons.accepted.connect(dialog.accept)
        buttons.rejected.connect(dialog.reject)
        form.addRow(buttons)
        if dialog.exec() != QDialog.DialogCode.Accepted:
            return
        source, path = self.current_path, paths[0]
        values = {key: box.isChecked() for key, box in boxes.items()}
        def job(progress=None, token=None):
            fs = FatImageFilesystem(source)
            try:
                return fs.set_attributes(path, **values)
            finally:
                fs.close()
        self._run_worker("Updating DOS attributes", job, on_result=lambda attrs: self._after_fs_change(f"Updated attributes: {attrs}"))

    def change_volume_label(self) -> None:
        if not isinstance(self.current_fs, FatImageFilesystem) or not self.current_path:
            return
        value, accepted = QInputDialog.getText(self, "Change volume label", "Volume label", text=self.current_fs.volume_label())
        if not accepted:
            return
        source = self.current_path
        def job(progress=None, token=None):
            fs = FatImageFilesystem(source)
            try:
                return fs.set_volume_label(value)
            finally:
                fs.close()
        self._run_worker("Updating volume label", job, on_result=lambda label: self._after_fs_change(f"Volume label: {label}"))

    def edit_image_comment(self) -> None:
        if not self.current_path:
            return
        dialog = QDialog(self)
        dialog.setWindowTitle("Edit image comment")
        layout = QVBoxLayout(dialog)
        editor = QPlainTextEdit(load_image_metadata(self.current_path).comment)
        editor.setPlaceholderText("Stored in a DiskForge sidecar file; image bytes are not changed.")
        layout.addWidget(editor)
        buttons = QDialogButtonBox(QDialogButtonBox.StandardButton.Save | QDialogButtonBox.StandardButton.Cancel)
        buttons.accepted.connect(dialog.accept)
        buttons.rejected.connect(dialog.reject)
        layout.addWidget(buttons)
        if dialog.exec() == QDialog.DialogCode.Accepted:
            metadata = save_image_comment(self.current_path, editor.toPlainText())
            self.log("Image comment saved")
            self._show_info()

    def resize_current_image(self) -> None:
        if not self.current_path:
            return
        dialog = QDialog(self)
        dialog.setWindowTitle("Resize image")
        form = QFormLayout(dialog)
        size = QLineEdit(str(self.current_path.stat().st_size))
        form.addRow("New size in bytes (multiple of 512)", size)
        notice = QLabel("A new image is created. FAT images are rebuilt; raw images cannot be shrunk if non-zero data would be discarded.")
        notice.setWordWrap(True)
        form.addRow(notice)
        buttons = QDialogButtonBox(QDialogButtonBox.StandardButton.Ok | QDialogButtonBox.StandardButton.Cancel)
        buttons.accepted.connect(dialog.accept)
        buttons.rejected.connect(dialog.reject)
        form.addRow(buttons)
        if dialog.exec() != QDialog.DialogCode.Accepted:
            return
        try:
            requested = int(size.text().strip())
        except ValueError:
            QMessageBox.warning(self, "Invalid size", "Enter a whole number of bytes.")
            return
        output, _ = QFileDialog.getSaveFileName(self, "Save resized image", str(self.current_path.with_stem(self.current_path.stem + "-resized")), "Disk image (*.img);;All files (*)")
        if output:
            self._run_worker("Resizing image", resize_image, self.current_path, Path(output), requested, on_result=lambda result: self._open_path(result.destination))

    def compare_current_image(self) -> None:
        if not self.current_path:
            return
        other, _ = QFileDialog.getOpenFileName(self, "Compare image with", str(self.current_path.parent), IMAGE_FILTER)
        if not other:
            return
        def completed(result) -> None:
            message = "Images are byte-identical." if result.equal else f"Difference: {result.reason}; first offset: {result.first_difference}"
            self.log(message)
            QMessageBox.information(self, "Image comparison", message)
        self._run_worker("Comparing images", compare_streams, self.current_path, Path(other), on_result=completed)

    def create_bundle(self) -> None:
        if not self.current_path:
            return
        dialog = QDialog(self)
        dialog.setWindowTitle("Create secure image bundle")
        form = QFormLayout(dialog)
        comment = QLineEdit()
        description = QLineEdit()
        password = QLineEdit()
        password.setEchoMode(QLineEdit.EchoMode.Password)
        confirm = QLineEdit()
        confirm.setEchoMode(QLineEdit.EchoMode.Password)
        compression = QComboBox()
        for level in range(10):
            compression.addItem(str(level), level)
        compression.setCurrentIndex(6)
        form.addRow("Comment", comment)
        form.addRow("Description", description)
        form.addRow("Password (optional)", password)
        form.addRow("Confirm password", confirm)
        form.addRow("Compression level", compression)
        buttons = QDialogButtonBox(QDialogButtonBox.StandardButton.Ok | QDialogButtonBox.StandardButton.Cancel)
        buttons.accepted.connect(dialog.accept)
        buttons.rejected.connect(dialog.reject)
        form.addRow(buttons)
        if dialog.exec() != QDialog.DialogCode.Accepted:
            return
        if password.text() != confirm.text():
            QMessageBox.warning(self, "Password mismatch", "The two password fields do not match.")
            return
        output, _ = QFileDialog.getSaveFileName(self, "Create DiskForge bundle", str(self.current_path.with_suffix(".dfb")), "DiskForge bundle (*.dfb)")
        if output:
            secret = password.text() or None
            self._run_worker("Creating secure image bundle", create_bundle, [self.current_path], Path(output), password=secret,
                             comment=comment.text(), description=description.text(), compression_level=compression.currentData(),
                             on_result=lambda info: self.log(f"Created bundle: {info.path}"))

    def wrap_current_fat_in_mbr(self) -> None:
        """Write a separate neutral-MBR wrapper; the source image is never changed."""
        if not self.current_path or not self.current_info or self.current_info.filesystem not in {FileSystemType.FAT12, FileSystemType.FAT16, FileSystemType.FAT32}:
            return
        output, _ = QFileDialog.getSaveFileName(
            self, "Save MBR-wrapped FAT image", str(self.current_path.with_stem(self.current_path.stem + "-mbr")),
            "Disk image (*.img *.ima);;All files (*)",
        )
        if not output:
            return
        self._run_worker(
            "Creating MBR-wrapped FAT image", wrap_fat_image_in_mbr, self.current_path, Path(output),
            on_result=lambda result: self._open_path(result.path),
        )

    def prepare_current_fat_deployment(self) -> None:
        """Prepare and review a neutral-MBR copy before any device is selected."""
        if not self.current_path or not self.current_info or self.current_info.filesystem not in {FileSystemType.FAT12, FileSystemType.FAT16, FileSystemType.FAT32}:
            return
        answer = QMessageBox.question(
            self, "Prepare FAT deployment", "Create a new neutral-MBR deployment image? The current image will not be changed. Any physical write still requires selecting a device and entering ERASE.",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.Cancel, QMessageBox.StandardButton.Yes,
        )
        if answer != QMessageBox.StandardButton.Yes:
            return
        output, _ = QFileDialog.getSaveFileName(
            self, "Save prepared deployment image", str(self.current_path.with_stem(self.current_path.stem + "-deploy")),
            "Disk image (*.img *.ima);;All files (*)",
        )
        if not output:
            return
        self._run_worker(
            "Preparing FAT deployment image", prepare_fat_deployment, self.current_path, Path(output),
            on_result=self._deployment_plan_ready,
        )

    def _deployment_plan_ready(self, plan) -> None:  # type: ignore[no-untyped-def]
        details = (
            f"Prepared image: {plan.prepared_image}\n"
            f"Single FAT partition: LBA {plan.partition_start_lba}, {plan.partition_sectors} sectors\n"
            f"Partition type: 0x{plan.partition_type:02X}\n\n"
            "No physical device has been written. Use Physical drive operations and enter ERASE there if you choose to deploy this prepared image."
        )
        QMessageBox.information(self, "Deployment plan ready", details)
        self.log(f"Prepared FAT deployment image: {plan.prepared_image}")

    def trim_current_zero_tail(self) -> None:
        """Create a copy after removing only trailing, whole zero-filled sectors."""
        if not self.current_path:
            return
        value, accepted = QInputDialog.getText(
            self, "Trim trailing zero sectors", "Minimum retained size in bytes (multiple of 512)", text="512",
        )
        if not accepted:
            return
        try:
            minimum_size = int(value.strip())
        except ValueError:
            QMessageBox.warning(self, "Invalid minimum size", "Enter a whole number of bytes.")
            return
        if minimum_size < 0 or minimum_size % 512 or minimum_size > self.current_path.stat().st_size:
            QMessageBox.warning(self, "Invalid minimum size", "The value must be a non-negative multiple of 512 and cannot exceed the image size.")
            return
        answer = QMessageBox.warning(
            self, "Trim trailing zero sectors",
            "This creates a new raw image after removing only full zero-filled sectors at the end. It does not repair filesystem or partition metadata. Continue?",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.Cancel, QMessageBox.StandardButton.Cancel,
        )
        if answer != QMessageBox.StandardButton.Yes:
            return
        output, _ = QFileDialog.getSaveFileName(
            self, "Save trimmed image", str(self.current_path.with_stem(self.current_path.stem + "-trimmed")),
            "Disk image (*.img *.ima *.bin);;All files (*)",
        )
        if not output:
            return
        self._run_worker(
            "Trimming trailing zero sectors", trim_zero_tail, self.current_path, Path(output), minimum_size=minimum_size,
            on_result=lambda result: self._trim_complete(result),
        )

    def _trim_complete(self, result) -> None:  # type: ignore[no-untyped-def]
        self.log(f"Trimmed {human_bytes(result.bytes_removed)} from {result.source.name}")
        self._open_path(result.destination)

    def inspect_iso_boot(self) -> None:
        """Inspect a boot catalog first, then optionally export one declared boot image."""
        if not self.current_path:
            return
        source = self.current_path
        self._run_worker(
            "Inspecting El Torito boot catalog", lambda progress=None, token=None: inspect_eltorito(source),
            on_result=self._show_iso_boot_catalog,
        )

    def _show_iso_boot_catalog(self, catalog) -> None:  # type: ignore[no-untyped-def]
        rows = [f"Catalog LBA: {catalog.catalog_lba}", ""]
        for image in catalog.images:
            rows.append(
                f"{image.index}: {'bootable' if image.bootable else 'not bootable'} · LBA {image.lba} · "
                f"{human_bytes(image.byte_count)} · media type 0x{image.media_type:02X} · system 0x{image.system_type:02X}"
            )
        dialog = QMessageBox(self)
        dialog.setWindowTitle("ISO boot catalog")
        dialog.setIcon(QMessageBox.Icon.Information)
        dialog.setText("El Torito boot images are available for read-only export.")
        dialog.setDetailedText("\n".join(rows))
        export_button = dialog.addButton("Export boot image…", QMessageBox.ButtonRole.ActionRole)
        dialog.addButton(QMessageBox.StandardButton.Close)
        dialog.exec()
        if dialog.clickedButton() != export_button:
            return
        index, accepted = QInputDialog.getInt(self, "Export boot image", "Catalog image index", 0, 0, len(catalog.images) - 1)
        if not accepted:
            return
        output, _ = QFileDialog.getSaveFileName(
            self, "Export El Torito boot image", f"{catalog.iso_path.stem}-boot-{index}.img",
            "Boot image (*.img *.ima *.bin);;All files (*)",
        )
        if output:
            self._run_worker(
                "Exporting El Torito boot image", export_boot_image, catalog.iso_path, Path(output), index=index,
                on_result=lambda path: self.log(f"Exported ISO boot image: {path}"),
            )

    def defragment_image(self) -> None:
        if not isinstance(self.current_fs, FatImageFilesystem) or not self.current_path:
            return
        output, _ = QFileDialog.getSaveFileName(self, "Save defragmented FAT image", str(self.current_path.with_stem(self.current_path.stem + "-defragmented")), "Disk image (*.img)")
        if not output:
            return
        answer = QMessageBox.question(self, "Rebuild FAT image", "DiskForge will create a new image and write the files in order for a compact FAT allocation. The original is unchanged. Continue?", QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.Cancel, QMessageBox.StandardButton.Cancel)
        if answer != QMessageBox.StandardButton.Yes:
            return
        self._run_worker("Defragmenting FAT image", defragment_fat_image, self.current_path, Path(output), on_result=lambda result: self._open_path(Path(result)))

    @staticmethod
    def _listing_html(entries: Sequence[ImageEntry], source: Path) -> str:
        return directory_listing_html(entries, source)

    def _complete_listing_entries(self, token=None) -> list[ImageEntry]:
        if not self.current_fs:
            raise DiskForgeError("The current image has no browsable filesystem.")
        return collect_directory_listing(self.current_fs, token=token)

    def print_listing(self) -> None:
        if not self.current_fs or not self.current_path:
            return
        try:
            entries = self._complete_listing_entries()
            document = QTextDocument()
            document.setHtml(self._listing_html(entries, self.current_path))
            printer = QPrinter(QPrinter.PrinterMode.HighResolution)
            dialog = QPrintDialog(printer, self)
            if dialog.exec() == QDialog.DialogCode.Accepted:
                document.print_(printer)
                self.log("Directory listing sent to printer")
        except Exception as exc:
            QMessageBox.critical(self, "Unable to print listing", str(exc))

    def _after_fs_change(self, message: str) -> None:
        self.log(message)
        if self.current_path:
            editable_fixed_vhd = self._editable_fixed_vhd
            if editable_fixed_vhd:
                try:
                    validate_fixed_vhd_fat(self.current_path)
                except Exception as exc:
                    self._editable_fixed_vhd = False
                    QMessageBox.critical(self, "Fixed VHD validation failed", str(exc))
                    return
            self._open_path(self.current_path, editable_fixed_vhd=editable_fixed_vhd)

    def convert_image(self) -> None:
        if not self.current_path:
            return
        dialog = ConvertDialog(self.current_path, self)
        if dialog.exec() != QDialog.DialogCode.Accepted or not dialog.destination.text().strip():
            return
        target = Path(dialog.destination.text())
        qemu = QemuImgConverter(self.settings.value("qemu_img_path", "") or None)
        self._run_worker("Converting image", convert_image, self.current_path, target, dialog.format.currentData(), qemu, on_result=lambda info: self._open_path(info.path), overwrite=dialog.overwrite.isChecked())

    def verify_image(self) -> None:
        if self.current_path:
            self._run_worker("Calculating SHA-256", sha256_file, self.current_path, on_result=lambda digest: self._verified(digest))

    def _verified(self, digest: str) -> None:
        self.log(f"SHA-256: {digest}")
        QMessageBox.information(self, "SHA-256 verified", digest)

    def export_listing(self) -> None:
        if not self.current_fs or not self.current_path:
            QMessageBox.information(
                self, self._localized("Listing unavailable"),
                self._localized("Open a browsable FAT, ISO, NTFS, EXT, HFS, or HFS+ image first."),
            )
            return
        output, selected = QFileDialog.getSaveFileName(self, "Export image listing", f"{self.current_path.stem}-listing.html", "HTML (*.html);;Text (*.txt)")
        if not output:
            return
        html_output = output.lower().endswith((".html", ".htm"))
        source = self.current_path
        def job(progress=None, token=None):
            return export_directory_listing(self.current_fs, source, Path(output), html=html_output, token=token)
        self._run_worker("Exporting directory listing", job, on_result=lambda path: self.log(f"Exported listing: {path}"))

    def batch_read_physical_media(self) -> None:
        """Queue selected removable/optical devices for read-only acquisition."""
        dialog = QDialog(self)
        dialog.setWindowTitle("Batch read physical media")
        dialog.resize(650, 430)
        layout = QVBoxLayout(dialog)
        notice = QLabel("This workflow only reads selected removable or optical media into new image files. It never writes to a physical device. Each completed image receives a SHA-256 audit entry.")
        notice.setWordWrap(True)
        layout.addWidget(notice)
        choices = QListWidget()
        choices.setSelectionMode(QAbstractItemView.SelectionMode.MultiSelection)
        for device in list_devices():
            if device.size <= 0 or not (device.removable or device.kind == DeviceKind.OPTICAL):
                continue
            item = QListWidgetItem(f"{device.display_name} · {human_bytes(device.size)} · {device.identifier}")
            item.setData(Qt.ItemDataRole.UserRole, device)
            choices.addItem(item)
        layout.addWidget(choices, 1)
        output = QLineEdit(str(self.settings.value("last_directory", "")))
        browse = QPushButton("Browse…")
        def choose_output() -> None:
            directory = QFileDialog.getExistingDirectory(dialog, "Choose acquisition output directory", output.text())
            if directory:
                output.setText(directory)
        browse.clicked.connect(choose_output)
        output_row = QHBoxLayout()
        output_row.addWidget(output)
        output_row.addWidget(browse)
        layout.addWidget(QLabel("Output directory"))
        layout.addLayout(output_row)
        continue_on_error = QCheckBox("Continue after a failed read")
        layout.addWidget(continue_on_error)
        buttons = QDialogButtonBox(QDialogButtonBox.StandardButton.Ok | QDialogButtonBox.StandardButton.Cancel)
        buttons.accepted.connect(dialog.accept)
        buttons.rejected.connect(dialog.reject)
        layout.addWidget(buttons)
        if dialog.exec() != QDialog.DialogCode.Accepted:
            return
        directory = Path(output.text().strip())
        selected = [choices.item(index).data(Qt.ItemDataRole.UserRole) for index in range(choices.count()) if choices.item(index).isSelected()]
        if not selected or not directory.is_dir():
            QMessageBox.warning(self, "Read queue requires selections", "Select one or more removable or optical media and an existing output directory.")
            return
        timestamp = datetime.now().strftime("%Y%m%d-%H%M%S")
        requests: list[DeviceReadRequest] = []
        for index, device in enumerate(selected, start=1):
            safe_name = "".join(character if character.isalnum() else "-" for character in device.display_name).strip("-") or "media"
            requests.append(DeviceReadRequest(device, directory / f"{timestamp}-{index:02d}-{safe_name}.img"))
        def read_queue(progress=None, token=None):
            return read_device_queue(requests, continue_on_error=continue_on_error.isChecked(), progress=progress, token=token)
        def show_report(report) -> None:  # type: ignore[no-untyped-def]
            summary = "\n".join(
                f"{'OK' if item.error is None else 'FAILED'}  {item.device}  →  {item.destination}\n"
                f"{item.sha256 or item.error or ''}" for item in report.items
            )
            QMessageBox.information(self, "Read-only acquisition report", f"Succeeded: {report.succeeded}; failed: {report.failed}\n\n{summary}")
        self._run_worker("Reading physical media queue", read_queue, on_result=show_report)

    def edit_boot_sector(self) -> None:
        if self.current_path:
            BootSectorDialog(self.current_path, self).exec()
            self._open_path(self.current_path)

    def show_partitions(self) -> None:
        if not self.current_path:
            return
        try:
            parts = list_partitions(self.current_path)
            if not parts:
                QMessageBox.information(self, "Partitions", "No MBR or GPT partitions found. This may be a superfloppy image.")
                return
            labels = [
                f"{part.index}: LBA {part.start_lba} · {human_bytes(part.size)} · {part.filesystem.value} · {part.name or part.type_code}"
                for part in parts
            ]
            selected, accepted = QInputDialog.getItem(
                self,
                self._localized("Partition table"),
                self._localized("Choose a partition to browse. FAT retains the existing edit path; NTFS, EXT, HFS, and HFS+ stay read-only."),
                labels, 0, False,
            )
            if not accepted:
                return
            partition = parts[labels.index(selected)]
            supported = {
                FileSystemType.FAT12, FileSystemType.FAT16, FileSystemType.FAT32,
                FileSystemType.NTFS, FileSystemType.EXT, FileSystemType.HFS, FileSystemType.HFS_PLUS,
            }
            if partition.filesystem not in supported:
                QMessageBox.information(
                    self,
                    self._localized("Partition is unsupported"),
                    self._localized("This partition is not a supported FAT, NTFS, EXT, HFS, or HFS+ filesystem."),
                )
                return
            image = self.current_path
            self._open_path(image, partition_index=partition.index)
            mode = "FAT" if partition.filesystem in {FileSystemType.FAT12, FileSystemType.FAT16, FileSystemType.FAT32} else self._localized("read-only")
            self.log(self._localized("Opened {mode} partition {index} from {name}").format(
                mode=mode, index=partition.index, name=image.name,
            ))
        except Exception as exc:
            QMessageBox.critical(self, "Unable to read partitions", str(exc))

    def create_legacy_zip(self) -> None:
        """Create a conservative single-payload IMZ/WLZ ZIP-compatible copy."""
        if not self.current_path:
            return
        source = self.current_path
        format_name, accepted = QInputDialog.getItem(self, "Create ZIP-compatible legacy image", "Container format:", ["IMZ", "WLZ"], 0, False)
        if not accepted:
            return
        image_format = ImageFormat.IMZ if format_name == "IMZ" else ImageFormat.WLZ
        default = source.with_suffix(f".{image_format.value}")
        output, _ = QFileDialog.getSaveFileName(self, "Save ZIP-compatible legacy image", str(default),
                                                "IMZ image (*.imz);;WLZ image (*.wlz)")
        if not output:
            return
        destination = Path(output)
        if destination.resolve() == source.resolve():
            QMessageBox.warning(self, "Separate output required", "Choose a different output file; the source image remains unchanged.")
            return
        self._run_worker("Creating ZIP-compatible legacy image", create_legacy_zip_image, source, destination,
                         image_format, on_result=lambda result: self._open_path(result.destination))

    def create_sfx(self) -> None:
        if not self.current_path:
            return
        output, _ = QFileDialog.getSaveFileName(self, "Create self-extracting bundle", f"{self.current_path.stem}.pyz", "Python zipapp (*.pyz)")
        if output:
            source = self.current_path
            def job(progress=None, token=None):
                return create_self_extractor(source, Path(output))
            self._run_worker("Creating self-extracting bundle", job, on_result=lambda path: self.log(f"Self-extractor created: {path}"))

    def physical_drive(self) -> None:
        dialog = DeviceDialog(self.current_path, self)
        result = dialog.exec()
        operation = dialog.property("operation")
        if not operation:
            return
        if operation[0] == "read":
            _, device, destination = operation
            self._run_worker("Reading physical drive", read_device_to_image, device, destination, on_result=lambda path: self._open_path(Path(path)), overwrite=True)
        elif operation[0] == "write":
            _, device, image, phrase, verify = operation
            self._run_worker("Writing physical drive", write_image_to_device, image, device, phrase, on_result=lambda ok: QMessageBox.information(self, "Physical write complete", "The image was written and verified." if ok else "The image was written."), verify_after_write=verify)
        elif operation[0] == "mbr_backup":
            _, device, destination = operation
            self._run_worker("Backing up device MBR", backup_device_mbr, device, destination,
                             on_result=lambda result: QMessageBox.information(self, "MBR backup complete", f"Verified MBR backup created:\n{result.backup}"))
        elif operation[0] == "mbr_neutralize":
            _, device, destination, phrase = operation
            self._run_worker("Neutralizing device MBR", neutralize_device_mbr, device, destination, phrase,
                             on_result=lambda result: QMessageBox.information(self, "Device MBR neutralized", f"Readback verification succeeded. Backup created:\n{result.backup}"))
        elif operation[0] == "mbr_restore":
            _, device, backup, destination, phrase = operation
            self._run_worker("Restoring device MBR", restore_device_mbr, device, backup, destination, phrase,
                             on_result=lambda result: QMessageBox.information(self, "Device MBR restored", f"Readback verification succeeded. Backup created:\n{result.backup}"))
        elif operation[0] == "format_controller_floppy":
            _, device, phrase = operation
            self._run_worker("Formatting controller floppy", FloppyControllerFormatter().format, device, phrase,
                             on_result=lambda result: QMessageBox.information(self, "Controller floppy formatted", "Low-level format completed with backend verification."))
        elif operation[0] == "format_ufi_floppy":
            _, device, capacity, phrase = operation
            self._run_worker("Formatting UFI USB floppy", FloppyControllerFormatter().format_usb, device, capacity, phrase,
                             on_result=lambda result: QMessageBox.information(self, "UFI USB floppy formatted", "Low-level UFI formatting completed with backend verification."))
        elif operation[0] == "format_removable_fat":
            _, device, filesystem, label, phrase = operation
            self._run_worker("Formatting removable FAT media", format_removable_fat, device, filesystem, label, phrase,
                             on_result=lambda result: QMessageBox.information(self, "Removable media formatted", f"{result.label} was formatted and reopened successfully."))

    def design_batch(self, existing_recipe: Path | None = None) -> None:
        try:
            dialog = BatchDesignerDialog.from_path(existing_recipe, self) if existing_recipe else BatchDesignerDialog(self)
        except DiskForgeError as exc:
            QMessageBox.warning(self, "Batch recipe rejected", str(exc))
            return
        if dialog.exec() != QDialog.DialogCode.Accepted:
            return
        try:
            recipe = dialog.recipe()
        except DiskForgeError as exc:
            QMessageBox.warning(self, "Batch recipe is incomplete", str(exc))
            return
        output = str(existing_recipe) if existing_recipe else ""
        if not output:
            output, _ = QFileDialog.getSaveFileName(self, "Save batch recipe", "diskforge-workflow.json", "DiskForge batch (*.json)")
        if not output:
            return
        try:
            target = dialog.write_recipe(Path(output))
        except DiskForgeError as exc:
            QMessageBox.warning(self, "Unable to save batch recipe", str(exc))
            return
        try:
            plan = BatchRunner(QemuImgConverter(self.settings.value("qemu_img_path", "") or None)).preview(target)
        except DiskForgeError as exc:
            QMessageBox.warning(self, "Batch recipe rejected", str(exc))
            return
        summary = "\n".join(
            f"{item['index'] + 1}. {item['kind']} — {'writes output' if item['will_write'] else 'read-only'}"
            for item in plan
        )
        answer = QMessageBox.question(
            self, "Batch recipe saved", f"Saved safe extraction recipe:\n{target}\n\nPreflight plan:\n{summary}\n\nRun it now?",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No, QMessageBox.StandardButton.Yes,
        )
        if answer == QMessageBox.StandardButton.Yes:
            self._run_batch_path(target)
        else:
            self.log(f"Batch recipe saved: {target}")

    def _run_batch_path(self, path: Path) -> None:
        try:
            plan = BatchRunner(QemuImgConverter(self.settings.value("qemu_img_path", "") or None)).preview(path)
        except DiskForgeError as exc:
            QMessageBox.warning(self, "Batch recipe rejected", str(exc))
            return
        summary = "\n".join(f"{item['index'] + 1}. {item['kind']}" for item in plan)
        answer = QMessageBox.question(
            self, "Review batch plan", f"The following recipe has passed preflight:\n{summary}\n\nRun it now?",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No, QMessageBox.StandardButton.Yes,
        )
        if answer != QMessageBox.StandardButton.Yes:
            self.log("Batch execution cancelled after preflight review.")
            return
        def job(progress=None, token=None):
            return BatchRunner(QemuImgConverter(self.settings.value("qemu_img_path", "") or None)).run(path, self.log)
        self._run_worker("Running batch recipe", job, on_result=lambda result: BatchResultDialog(result, self).exec())

    def edit_batch(self) -> None:
        path, _ = QFileDialog.getOpenFileName(self, "Edit batch recipe", "", "DiskForge batch (*.json);;All files (*)")
        if path:
            self.design_batch(Path(path))

    def run_batch(self) -> None:
        path, _ = QFileDialog.getOpenFileName(self, "Run batch recipe", "", "DiskForge batch (*.json);;All files (*)")
        if not path:
            return
        self._run_batch_path(Path(path))

    def _apply_interface_font(self) -> None:
        app = QApplication.instance()
        if app is None:
            return
        current = app.font()
        family = str(self.settings.value("interface_font_family", current.family()))
        size = int(self.settings.value("interface_font_size", current.pointSize() if current.pointSize() > 0 else 10))
        font = QFont(current)
        font.setFamily(family)
        font.setPointSize(max(8, min(size, 28)))
        app.setFont(font)

    def preferences(self) -> None:
        dialog = QDialog(self)
        dialog.setWindowTitle("Preferences")
        layout = QFormLayout(dialog)
        appearance = QComboBox()
        appearance.addItem("Light", "light")
        appearance.addItem("Midnight", "dark")
        appearance.setCurrentIndex(1 if str(self.settings.value("appearance", "light")) == "dark" else 0)
        layout.addRow("Appearance", appearance)
        font_family = QFontComboBox()
        saved_family = str(self.settings.value("interface_font_family", QApplication.font().family()))
        font_family.setCurrentFont(QFont(saved_family))
        font_size = QSpinBox()
        font_size.setRange(8, 28)
        font_size.setValue(int(self.settings.value("interface_font_size", QApplication.font().pointSize() or 10)))
        layout.addRow("Interface font", font_family)
        layout.addRow("Interface font size", font_size)
        qemu_path = QLineEdit(str(self.settings.value("qemu_img_path", "")))
        browse = QPushButton("Browse…")
        def choose() -> None:
            path, _ = QFileDialog.getOpenFileName(dialog, "Locate qemu-img executable")
            if path:
                qemu_path.setText(path)
        browse.clicked.connect(choose)
        row = QHBoxLayout()
        row.addWidget(qemu_path)
        row.addWidget(browse)
        layout.addRow("Optional qemu-img executable", row)
        details = QLabel("qemu-img enables VHDX, VMDK and QCOW2 inspection/conversion. DiskForge never downloads it automatically.")
        details.setWordWrap(True)
        layout.addRow(details)
        dmg_path = QLineEdit(str(self.settings.value("dmg2img_path", "")))
        dmg_browse = QPushButton("Browse…")
        def choose_dmg() -> None:
            path, _ = QFileDialog.getOpenFileName(dialog, "Locate dmg2img executable")
            if path:
                dmg_path.setText(path)
        dmg_browse.clicked.connect(choose_dmg)
        dmg_row = QHBoxLayout()
        dmg_row.addWidget(dmg_path)
        dmg_row.addWidget(dmg_browse)
        layout.addRow("Optional dmg2img executable", dmg_row)
        dmg_details = QLabel("dmg2img can convert a DMG into a new raw HFS+ image. DiskForge does not mount or write DMG files, and never downloads the adapter automatically.")
        dmg_details.setWordWrap(True)
        layout.addRow(dmg_details)
        buttons = QDialogButtonBox(QDialogButtonBox.StandardButton.Save | QDialogButtonBox.StandardButton.Cancel)
        buttons.accepted.connect(dialog.accept)
        buttons.rejected.connect(dialog.reject)
        layout.addRow(buttons)
        if dialog.exec() == QDialog.DialogCode.Accepted:
            self.settings.setValue("qemu_img_path", qemu_path.text().strip())
            self.settings.setValue("dmg2img_path", dmg_path.text().strip())
            self.settings.setValue("appearance", appearance.currentData())
            self.settings.setValue("interface_font_family", font_family.currentFont().family())
            self.settings.setValue("interface_font_size", font_size.value())
            apply_theme(QApplication.instance(), str(appearance.currentData()))
            self._apply_interface_font()
            self.log("Preferences saved")

    def about(self) -> None:
        try:
            translate = language_manager().text
        except RuntimeError:
            translate = lambda value: value
        overview = translate("DiskForge is a cross-platform workspace for opening, editing, checking and distributing disk images.")
        workflow = translate("Work with FAT, ISO, RAW and virtual-disk images through explicit, safe workflows. Optional converters and read-only adapters are shown only when configured.")
        QMessageBox.about(self, translate("About DiskForge"), f"<h2>DiskForge</h2><p>{overview}</p><p>{workflow}</p>")
