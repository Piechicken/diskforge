from __future__ import annotations

from PySide6.QtCore import QSettings, Qt
from PySide6.QtWidgets import QApplication, QPushButton

from diskforge.gui.i18n import LANGUAGES, LanguageManager


def _application() -> QApplication:
    return QApplication.instance() or QApplication([])


def test_required_un_languages_and_japanese_are_registered() -> None:
    codes = {language.code for language in LANGUAGES}
    assert {"ar", "zh_CN", "en", "fr", "ru", "es", "ja"} <= codes


def test_language_manager_translates_switches_and_enables_rtl(tmp_path) -> None:  # type: ignore[no-untyped-def]
    app = _application()
    settings = QSettings(str(tmp_path / "preferences.ini"), QSettings.Format.IniFormat)
    manager = LanguageManager(app, settings)
    button = QPushButton("Cancel")

    manager.set_language("ar")
    manager.apply_widget(button)
    assert app.layoutDirection() == Qt.LayoutDirection.RightToLeft
    assert button.text() == "إلغاء"
    assert settings.value("ui_language") == "ar"

    manager.set_language("es")
    manager.apply_widget(button)
    assert app.layoutDirection() == Qt.LayoutDirection.LeftToRight
    assert button.text() == "Cancelar"


def test_all_supported_languages_can_be_selected(tmp_path) -> None:  # type: ignore[no-untyped-def]
    app = _application()
    manager = LanguageManager(app, QSettings(str(tmp_path / "languages.ini"), QSettings.Format.IniFormat))
    for language in LANGUAGES:
        manager.set_language(language.code)
        assert manager.language.code == language.code


def test_workspace_and_preview_labels_are_translated_in_every_non_english_locale() -> None:
    from diskforge.gui.i18n import CATALOG

    required = {
        "DiskForge Workspace",
        "Preparing file preview",
        "Preview unavailable",
        "Image preview",
        "Text preview",
        "ZIP archive contents",
        "CAB archive contents",
        "InstallShield setup data",
        "DOS MZ executable",
        "Binary inspection",
        "Find in document",
        "Save copy…",
        "Save back to image",
        "Document details",
        "Editable text: save a copy or write back to a writable FAT image.",
        "Sleuth Kit browsing is available only for NTFS, EXT, HFS and HFS+ filesystems.",
    }
    for language in LANGUAGES:
        if language.code == "en":
            continue
        translated = CATALOG[language.code]
        assert required <= set(translated)
        assert all(translated[source] != source for source in required)


def test_template_layout_workflow_is_translated_in_every_non_english_locale() -> None:
    from diskforge.gui.i18n import CATALOG

    required = {
        "FAT image from template layout",
        "FAT layout template",
        "Reads a valid FAT BPB layout from a template image and creates a new editable image; the template is never modified.",
        "Choose FAT layout template",
        "FAT template required",
        "Choose a valid FAT image template before creating a layout-based image.",
        "Invalid FAT template",
        "Creating FAT image from template layout",
    }
    for language in LANGUAGES:
        if language.code == "en":
            continue
        translated = CATALOG[language.code]
        assert required <= set(translated)
        assert all(translated[source] != source for source in required)


def test_safe_boot_code_import_is_translated_in_every_non_english_locale() -> None:
    from diskforge.gui.i18n import CATALOG

    required = {
        "Import boot code safely…",
        "Import boot-sector file",
        "Import boot code safely",
        "The file must be a signed 512-byte boot sector. Only its executable boot-code area will be imported; the current FAT BPB is preserved and a complete image backup is created first. Continue?",
        "Boot code imported",
        "Boot code imported safely. Backup created:",
        "Unable to import boot code",
    }
    for language in LANGUAGES:
        if language.code == "en":
            continue
        translated = CATALOG[language.code]
        assert required <= set(translated)
        assert all(translated[source] != source for source in required)


def test_editable_fixed_vhd_workflow_is_translated_in_every_non_english_locale() -> None:
    from diskforge.gui.i18n import CATALOG

    required = {
        "Create editable fixed VHD copy…",
        "Create editable fixed VHD copy",
        "Separate output required",
        "Choose a different output file; the original fixed VHD is kept read-only.",
        "Creating editable fixed VHD copy",
        "Fixed VHD validation failed",
    }
    for language in LANGUAGES:
        if language.code == "en":
            continue
        translated = CATALOG[language.code]
        assert required <= set(translated)
        assert all(translated[source] != source for source in required)


def test_dmg_controlled_workflow_is_translated_in_every_non_english_locale() -> None:
    from diskforge.gui.i18n import CATALOG

    required = {
        "Convert DMG to raw image…",
        "Convert DMG to raw image",
        "DMG adapter unavailable",
        "Converting DMG to raw image",
        "Optional dmg2img executable",
        "Locate dmg2img executable",
        "dmg2img can convert a DMG into a new raw HFS+ image. DiskForge does not mount or write DMG files, and never downloads the adapter automatically.",
    }
    for language in LANGUAGES:
        if language.code == "en":
            continue
        translated = CATALOG[language.code]
        assert required <= set(translated)
        assert all(translated[source] != source for source in required)


def test_read_only_media_queue_is_translated_in_every_non_english_locale() -> None:
    from diskforge.gui.i18n import CATALOG

    required = {
        "Batch read physical media…",
        "Batch read physical media",
        "This workflow only reads selected removable or optical media into new image files. It never writes to a physical device. Each completed image receives a SHA-256 audit entry.",
        "Choose acquisition output directory",
        "Output directory",
        "Continue after a failed read",
        "Read queue requires selections",
        "Select one or more removable or optical media and an existing output directory.",
        "Reading physical media queue",
        "Read-only acquisition report",
    }
    for language in LANGUAGES:
        if language.code == "en":
            continue
        translated = CATALOG[language.code]
        assert required <= set(translated)
        assert all(translated[source] != source for source in required)


def test_safe_iso_replacement_and_partition_browsing_are_translated_in_every_non_english_locale() -> None:
    from diskforge.gui.i18n import CATALOG

    required = {
        "Safely replace ISO file…",
        "Select ISO file",
        "Select exactly one regular ISO file to replace safely.",
        "Select equal-size replacement file",
        "Save replaced ISO copy",
        "Separate output required",
        "The source ISO remains unchanged; choose a different output file.",
        "Safely replacing ISO file into a new image",
        "Partition table",
        "Partitions",
        "Unable to read partitions",
        "No MBR or GPT partitions found. This may be a superfloppy image.",
        "Choose a partition to browse. FAT retains the existing edit path; NTFS, EXT, HFS, and HFS+ stay read-only.",
        "Partition is unsupported",
        "This partition is not a supported FAT, NTFS, EXT, HFS, or HFS+ filesystem.",
        "read-only",
        "Opened {mode} partition {index} from {name}",
        "Listing unavailable",
        "Open a browsable FAT, ISO, NTFS, EXT, HFS, or HFS+ image first.",
    }
    for language in LANGUAGES:
        if language.code == "en":
            continue
        translated = CATALOG[language.code]
        assert required <= set(translated)
        assert all(translated[source] != source for source in required)


def test_device_mbr_and_removable_format_workflow_is_translated_in_every_non_english_locale() -> None:
    from diskforge.gui.i18n import CATALOG

    required = {
        "Removable format filesystem",
        "Removable format label",
        "Type FORMAT to erase and format removable media",
        "Type FORMAT to format",
        "Back up selected MBR…",
        "Neutralize selected MBR",
        "Format removable FAT media",
        "Back up selected device MBR",
        "Type ERASE exactly before changing a device MBR.",
        "Back up current MBR before neutralizing",
        "Type FORMAT exactly before formatting removable media.",
        "Backing up device MBR",
        "MBR backup complete",
        "Verified MBR backup created:",
        "Neutralizing device MBR",
        "Device MBR neutralized",
        "Readback verification succeeded. Backup created:",
        "Formatting removable FAT media",
        "Removable media formatted",
        " was formatted and reopened successfully.",
        "Restore selected MBR…",
        "Select MBR backup to restore",
        "Back up current MBR before restoring",
        "Restoring device MBR",
        "Device MBR restored",
    }
    for language in LANGUAGES:
        if language.code == "en":
            continue
        translated = CATALOG[language.code]
        assert required <= set(translated)
        assert all(translated[source] != source for source in required)


def test_read_only_mount_workflow_is_translated_in_every_non_english_locale() -> None:
    from diskforge.gui.i18n import CATALOG

    required = {
        "Mount image read-only…",
        "Unmount image",
        "Read-only mount unavailable",
        "Mounting image read-only",
        "Image mounted read-only",
        "The image is mounted read-only at:\n",
        "Unmounting image",
        "Image unmounted",
        "The DiskForge read-only mount session has been released.",
    }
    for language in LANGUAGES:
        if language.code == "en":
            continue
        translated = CATALOG[language.code]
        assert required <= set(translated)
        assert all(translated[source] != source for source in required)


def test_dynamic_vhd_workflow_is_translated_in_every_non_english_locale() -> None:
    from diskforge.gui.i18n import CATALOG

    required = {
        "Create dynamic VHD from FAT work image…",
        "Dynamic VHD adapter unavailable",
        "Create dynamic VHD from FAT work image",
        "Choose a different output file; the FAT work image remains unchanged.",
        "Creating verified dynamic VHD",
    }
    for language in LANGUAGES:
        if language.code == "en":
            continue
        translated = CATALOG[language.code]
        assert required <= set(translated)
        assert all(translated[source] != source for source in required)


def test_legacy_zip_workflow_is_translated_in_every_non_english_locale() -> None:
    from diskforge.gui.i18n import CATALOG

    required = {
        "Create ZIP-compatible legacy image…",
        "Create ZIP-compatible legacy image",
        "Container format:",
        "Save ZIP-compatible legacy image",
        "Choose a different output file; the source image remains unchanged.",
        "Creating ZIP-compatible legacy image",
    }
    for language in LANGUAGES:
        if language.code == "en":
            continue
        translated = CATALOG[language.code]
        assert required <= set(translated)
        assert all(translated[source] != source for source in required)


def test_controller_floppy_format_workflow_is_translated_in_every_non_english_locale() -> None:
    from diskforge.gui.i18n import CATALOG

    required = {
        "Type FORMAT_FLOPPY for controller-level floppy formatting",
        "Type FORMAT_FLOPPY for controller format",
        "Format controller floppy",
        "Type FORMAT_FLOPPY exactly before controller-level floppy formatting.",
        "Formatting controller floppy",
        "Controller floppy formatted",
        "Low-level format completed with backend verification.",
    }
    for language in LANGUAGES:
        if language.code == "en":
            continue
        translated = CATALOG[language.code]
        assert required <= set(translated)
        assert all(translated[source] != source for source in required)



def test_safe_iso_content_editing_is_translated_in_every_non_english_locale() -> None:
    from diskforge.gui.i18n import CATALOG

    required = {
        "Edit ISO content safely…",
        "Edit ISO content safely",
        "Add local file…",
        "Add local folder…",
        "Delete selected ISO entries",
        "Create ISO directory…",
        "Rebuilding ISO into a new image",
    }
    for language in LANGUAGES:
        if language.code == "en":
            continue
        translated = CATALOG[language.code]
        assert required <= set(translated)
        assert all(translated[source] != source for source in required)



def test_legacy_img_ima_floppy_workflow_is_translated_in_every_non_english_locale() -> None:
    from diskforge.gui.i18n import CATALOG

    required = {
        "Legacy FAT floppy image (IMG/IMA)",
        "Legacy floppy profile",
        "Legacy image format",
        "Use custom legacy geometry",
        "Custom CHS geometry",
        "Bytes/sector",
        "IMA floppy image (.ima)",
        "IMG raw image (.img)",
        "Raw IMG image (.img)",
        "Creates an editable FAT12 IMG or IMA with an explicit legacy floppy profile or custom geometry. The size is shown in KiB; no physical device is formatted.",
        "Create legacy floppy image",
        "Creating legacy FAT floppy image",
        "Creating custom legacy FAT floppy image",
    }
    for language in LANGUAGES:
        if language.code == "en":
            continue
        translated = CATALOG[language.code]
        assert required <= set(translated)
        assert all(translated[source] != source for source in required)



def test_controlled_filesystem_injection_is_translated_in_every_non_english_locale() -> None:
    from diskforge.gui.i18n import CATALOG

    required = {
        "Inject files safely into new NTFS/EXT image…",
        "Optional backend unavailable",
        "Safe NTFS/EXT injection",
        "This operation never changes the open image. It creates a separate output, accepts root-directory regular files only, refuses overwrite, and verifies every file after writing.",
        "Select regular local files",
        "Save verified output image",
        "Creating verified NTFS/EXT output",
        "Inject files safely into new NTFS/EXT/classic HFS image…",
        "Safe NTFS/EXT/classic HFS injection",
        "Classic HFS copies raw data forks only; HFS+ remains read-only.",
        "This operation never changes the open image. It creates a separate output, accepts root-directory regular files only, refuses overwrite, and verifies every file after writing. Classic HFS copies raw data forks only; HFS+ remains read-only.",
        "Creating verified NTFS/EXT/classic HFS output",
    }
    for language in LANGUAGES:
        if language.code == "en":
            continue
        translated = CATALOG[language.code]
        assert required <= set(translated)
        assert all(translated[source] != source for source in required)



def test_batch_designer_controlled_injection_is_translated_in_every_non_english_locale() -> None:
    from diskforge.gui.i18n import CATALOG

    required = {
        "Inject safely into new NTFS image",
        "Inject safely into new EXT image",
        "Copy a standalone NTFS image into a new output, add new root-level regular files, and verify every payload. Existing destinations and in-place changes are rejected.",
        "Copy a standalone EXT image into a new output, add new root-level regular files, and verify every payload. Existing destinations and in-place changes are rejected.",
        "Controlled NTFS/EXT injection requires a source image, new destination image, and local file paths.",
        "Inject safely into new classic HFS image",
        "Copy a standalone classic HFS image into a new output, add new root-level raw-data-fork files, and verify every payload. Existing destinations, in-place changes, HFS+, metadata, and resource forks are rejected.",
        "Controlled NTFS/EXT/classic HFS injection requires a source image, new destination image, and local file paths.",
    }
    for language in LANGUAGES:
        if language.code == "en":
            continue
        translated = CATALOG[language.code]
        assert required <= set(translated)
        assert all(translated[source] != source for source in required)


def test_classic_hfs_creation_is_translated_in_every_non_english_locale() -> None:
    from diskforge.gui.i18n import CATALOG

    required = {
        "Classic HFS image (optional hfsutils)",
        "Classic HFS size",
        "Creates a new standalone classic HFS file through an explicitly available hfsutils backend. The output is verified before opening; HFS+ and physical media are not included.",
        "Create classic HFS image",
        "Creating verified classic HFS image",
        "Create verified classic HFS image",
        "Create a new standalone classic HFS output through an explicitly available hfsutils backend. Choose a new destination, at least 800 KiB in 512-byte units, and a safe volume label. HFS+, physical media, partition maps, and overwrite are rejected.",
        "Classic HFS creation requires a new destination image, byte size, and volume label.",
        "Classic HFS creation byte size must be an integer.",
    }
    for language in LANGUAGES:
        if language.code == "en":
            continue
        translated = CATALOG[language.code]
        assert required <= set(translated)
        assert all(translated[source] != source for source in required)


def test_batch_directory_report_workflow_is_translated_in_every_non_english_locale() -> None:
    from diskforge.gui.i18n import CATALOG

    required = {
        "Export read-only directory listing",
        "Create HTML directory report",
        "Validated partition index (optional)",
        "Directory report format",
        "Write a new text or HTML directory report from a browsable image or an explicitly selected validated partition. NTFS, EXT, HFS, and HFS+ remain read-only.",
        "Directory report export requires a source image and a new report destination.",
        "Directory report partition index must be a positive integer.",
    }
    for language in LANGUAGES:
        if language.code == "en":
            continue
        translated = CATALOG[language.code]
        assert required <= set(translated)
        assert all(translated[source] != source for source in required)



def test_fat_file_move_workflow_is_translated_in_every_non_english_locale() -> None:
    from diskforge.gui.i18n import CATALOG

    required = {
        "Move to directory…",
        "Move image entry",
        "Existing target directory",
        "Moving image entry",
        "Moved entry to {path}",
        "Move regular FAT file",
        "Image file to move",
        "FAT target directory",
        "Move one regular file or complete directory tree within a writable FAT image to an existing image directory. Existing targets are never overwritten; directory movement uses cancellable copy-then-delete, requires a new same-name target outside the source tree, and is not claimed to be atomic.",
        "FAT file move requires a source image, an image file path, and an existing target directory.",
        "FAT file move partition index must be a positive integer.",
    }
    for language in LANGUAGES:
        if language.code == "en":
            continue
        translated = CATALOG[language.code]
        assert required <= set(translated)
        assert all(translated[source] != source for source in required)



def test_deleted_fat_recovery_workflow_is_translated_in_every_non_english_locale() -> None:
    from diskforge.gui.i18n import CATALOG

    required = {
        "Recover deleted FAT file…",
        "Scanning deleted FAT files",
        "Deleted FAT recovery candidates",
        "No recoverable deleted FAT12/FAT16 root-directory file candidates are available.",
        "Candidate recovery only copies one currently free cluster; it does not prove original contents, name, or integrity.",
        "Recover selected candidate",
        "Recover deleted FAT file",
        "Recovered files (*)",
        "Recovering deleted FAT file",
        "Recovered deleted-file candidate to {path}",
    }
    for language in LANGUAGES:
        if language.code == "en":
            continue
        translated = CATALOG[language.code]
        assert required <= set(translated)
        assert all(translated[source] != source for source in required)



def test_imd_inspection_workflow_is_translated_in_every_non_english_locale() -> None:
    from diskforge.gui.i18n import CATALOG

    required = {
        "Inspect / export IMD…",
        "Inspect IMD image",
        "ImageDisk files (*.imd);;All files (*)",
        "Inspecting IMD image",
        "IMD inspection",
        "Tracks",
        "RAW export",
        "Available",
        "Unavailable",
        "Reason",
        "Export proven RAW…",
        "Export proven RAW",
        "Raw image (*.img *.ima *.bin);;All files (*)",
        "Exporting IMD to RAW",
        "Exported proven IMD layout to {path}",
    }
    for language in LANGUAGES:
        if language.code == "en":
            continue
        translated = CATALOG[language.code]
        assert required <= set(translated)
        assert all(translated[source] != source for source in required)


def test_inventory_workflow_is_translated_in_every_non_english_locale() -> None:
    from diskforge.gui.i18n import CATALOG

    required = {
        "Inventory images…", "Inventory images", "Select directory to scan", "Inventory report",
        "Scanning image inventory", "Report format", "Include SHA-256", "Recursive scan",
        "Inventory complete: {count} images reported to {path}",
        "This workflow reads local image metadata and writes one new report; it never modifies source images.",
        "File suffix filter (optional)", "Image format filter", "Filesystem filter",
        "Minimum size (bytes)", "Maximum size (bytes)", "SHA-256 prefix (optional)",
        "Include partition summary", "Size filters must be whole numbers of bytes.",
    }
    for language in LANGUAGES:
        if language.code == "en":
            continue
        translated = CATALOG[language.code]
        assert required <= set(translated)
        assert all(translated[source] != source for source in required)


def test_td0_read_only_inspection_workflow_is_translated_in_every_non_english_locale() -> None:
    from diskforge.gui.i18n import CATALOG

    required = {
        "Inspect / export TD0…",
        "Inspect TD0 image",
        "TeleDisk files (*.td0);;All files (*)",
        "Inspecting TD0 image",
        "TD0 inspection",
        "Version",
        "Data rate",
        "Comment",
        "None",
        "sectors",
        "flags",
        "Exporting TD0 to RAW",
        "Exported proven TD0 layout to {path}",
    }
    for language in LANGUAGES:
        if language.code == "en":
            continue
        translated = CATALOG[language.code]
        assert required <= set(translated)
        assert all(translated[source] != source for source in required)


def test_multi_entry_fat_metadata_workflow_is_translated_in_every_non_english_locale() -> None:
    from diskforge.gui.i18n import CATALOG

    required = {
        "Modify FAT timestamps",
        "Timestamp value",
        "Created time",
        "Modified time",
        "Accessed time",
        "Apply to {count} selected item(s)",
        "No FAT timestamp fields selected",
        "Select at least one FAT timestamp field to update.",
        "Updating FAT metadata",
        "Updated FAT metadata for {count} item(s)",
        "No DOS attribute fields selected",
        "Select at least one DOS attribute field to update.",
    }
    for language in LANGUAGES:
        if language.code == "en":
            continue
        translated = CATALOG[language.code]
        assert required <= set(translated)
        assert all(translated[source] != source for source in required)


def test_dc42_read_only_inspection_workflow_is_translated_in_every_non_english_locale() -> None:
    from diskforge.gui.i18n import CATALOG

    required = {
        "Inspect / export DC42…",
        "Inspect DC42 image",
        "DC42 files (*.dc42);;All files (*)",
        "Inspecting DC42 image",
        "DC42 inspection",
        "Data fork",
        "Tag fork",
        "Encoding",
        "Format",
        "Exporting DC42 data fork to RAW",
        "Exported DC42 data fork to {path}",
    }
    for language in LANGUAGES:
        if language.code == "en":
            continue
        translated = CATALOG[language.code]
        assert required <= set(translated)
        assert all(translated[source] != source for source in required)


def test_twoimg_read_only_inspection_workflow_is_translated_in_every_non_english_locale() -> None:
    from diskforge.gui.i18n import CATALOG

    required = {
        "Inspect / export 2MG…",
        "Inspect 2MG image",
        "2MG files (*.2mg *.2img);;All files (*)",
        "Inspecting 2MG image",
        "2MG inspection",
        "Data block",
        "Volume number",
        "Write protected",
        "Creator data",
        "Exporting 2MG data block to RAW",
        "Exported 2MG data block to {path}",
    }
    for language in LANGUAGES:
        if language.code == "en":
            continue
        translated = CATALOG[language.code]
        assert required <= set(translated)
        assert all(translated[source] != source for source in required)


def test_apridisk_read_only_inspection_workflow_is_translated_in_every_non_english_locale() -> None:
    from diskforge.gui.i18n import CATALOG

    required = {
        "Inspect / export APRIDISK…",
        "Inspect APRIDISK image",
        "APRIDISK files (*.dsk);;All files (*)",
        "Inspecting APRIDISK image",
        "APRIDISK inspection",
        "Records",
        "Geometry",
        "Bytes per sector",
        "Deleted records",
        "Exporting APRIDISK to RAW",
        "Exported proven APRIDISK layout to {path}",
    }
    for language in LANGUAGES:
        if language.code == "en":
            continue
        translated = CATALOG[language.code]
        assert required <= set(translated)
        assert all(translated[source] != source for source in required)


def test_copyqm_read_only_inspection_workflow_is_translated_in_every_non_english_locale() -> None:
    from diskforge.gui.i18n import CATALOG

    required = {
        "Inspect / export CopyQM…",
        "Inspect CopyQM image",
        "CopyQM files (*.qm);;All files (*)",
        "Inspecting CopyQM image",
        "CopyQM inspection",
        "Data CRC",
        "Media description",
        "Density",
        "Validated bytes",
        "Exporting CopyQM to RAW",
        "Exported verified CopyQM image to {path}",
    }
    for language in LANGUAGES:
        if language.code == "en":
            continue
        translated = CATALOG[language.code]
        assert required <= set(translated)
        assert all(translated[source] != source for source in required)


def test_sap_read_only_inspection_workflow_is_translated_in_every_non_english_locale() -> None:
    from diskforge.gui.i18n import CATALOG

    required = {
        "Inspect / export SAP…",
        "Inspect SAP image",
        "SAP files (*.sap);;All files (*)",
        "Inspecting SAP image",
        "SAP inspection",
        "Disk type",
        "CRC errors",
        "Protected sectors",
        "Tracks per side",
        "Heads",
        "Sector records",
        "Exporting SAP to RAW",
        "Exported verified SAP layout to {path}",
    }
    for language in LANGUAGES:
        if language.code == "en":
            continue
        translated = CATALOG[language.code]
        assert required <= set(translated)
        assert all(translated[source] != source for source in required)


def test_msa_read_only_inspection_workflow_is_translated_in_every_non_english_locale() -> None:
    from diskforge.gui.i18n import CATALOG

    required = {
        "Inspect / export MSA…",
        "Inspect MSA image",
        "MSA files (*.msa);;All files (*)",
        "Inspecting MSA image",
        "MSA inspection",
        "Track range",
        "Compressed tracks",
        "Sectors per track",
        "Track records",
        "Exporting MSA to RAW",
        "Exported verified MSA tracks to {path}",
    }
    for language in LANGUAGES:
        if language.code == "en":
            continue
        translated = CATALOG[language.code]
        assert required <= set(translated)
        assert all(translated[source] != source for source in required)


def test_psi_read_only_inspection_workflow_is_translated_in_every_non_english_locale() -> None:
    from diskforge.gui.i18n import CATALOG

    required = {
        "Inspect / export PSI…",
        "Inspect PSI image",
        "PSI files (*.psi);;All files (*)",
        "Inspecting PSI image",
        "PSI inspection",
        "Compressed sectors",
        "Default format",
        "Comment chunks",
        "Metadata chunks",
        "Exporting PSI to RAW",
        "Exported verified PSI layout to {path}",
    }
    for language in LANGUAGES:
        if language.code == "en":
            continue
        translated = CATALOG[language.code]
        assert required <= set(translated)
        assert all(translated[source] != source for source in required)


def test_pri_structural_inspection_is_translated_in_every_non_english_locale() -> None:
    from diskforge.gui.i18n import CATALOG

    required = {
        "Inspect PRI structure…",
        "Inspect PRI structure",
        "PRI files (*.pri);;All files (*)",
        "Inspecting PRI structure",
        "PRI structural inspection",
        "Tracks with data",
        "Total bits",
        "Clock range",
        "Read-only bitstream",
        "No decoding or RAW export is available.",
        "Fuzzy events",
        "Clock events",
        "Weak events",
        "Unknown chunks",
    }
    for language in LANGUAGES:
        if language.code == "en":
            continue
        translated = CATALOG[language.code]
        assert required <= set(translated)
        assert all(translated[source] != source for source in required)


def test_86f_structural_inspection_is_translated_in_every_non_english_locale() -> None:
    from diskforge.gui.i18n import CATALOG

    required = {
        "Inspect 86F structure…",
        "Inspect 86F structure",
        "86F files (*.86f);;All files (*)",
        "Inspecting 86F structure",
        "86F structural inspection",
        "Missing tracks",
        "Sides",
        "Total bitcells",
        "Disk flags",
        "Surface description",
        "Offset table entries",
        "Encoded bytes",
        "Read-only bitstream",
        "No decoding or RAW export is available.",
    }
    for language in LANGUAGES:
        if language.code == "en":
            continue
        translated = CATALOG[language.code]
        assert required <= set(translated)
        assert all(translated[source] != source for source in required)


def test_fdi_structural_inspection_is_translated_in_every_non_english_locale() -> None:
    from diskforge.gui.i18n import CATALOG

    required = {
        "Inspect FDI structure…",
        "Inspect FDI structure",
        "FDI files (*.fdi);;All files (*)",
        "Inspecting FDI structure",
        "FDI structural inspection",
        "Blank tracks",
        "Cylinders",
        "Heads",
        "Media type",
        "Read-only container",
        "Creator",
        "Comment",
        "Rotation speed",
        "Disk TPI",
        "Head TPI",
        "Declared track bytes",
        "No decoding or RAW export is available.",
    }
    for language in LANGUAGES:
        if language.code == "en":
            continue
        translated = CATALOG[language.code]
        assert required <= set(translated)
        assert all(translated[source] != source for source in required)


def test_jv3_inspection_and_export_are_translated_in_every_non_english_locale() -> None:
    from diskforge.gui.i18n import CATALOG

    required = {
        "Inspect / export JV3…", "Inspect / export JV3", "JV3 files (*.jv3);;All files (*)",
        "Inspecting JV3 image", "JV3 inspection", "In-use sectors", "Free slots", "Header blocks",
        "Write protected", "Strict RAW export", "Geometry", "RAW bytes", "Unavailable", "Export reason",
        "Export JV3 RAW…", "Export JV3 RAW", "RAW images (*.img *.ima *.raw);;All files (*)",
        "Exporting JV3 RAW", "Exported JV3 RAW to {path}",
    }
    for language in LANGUAGES:
        if language.code == "en":
            continue
        translated = CATALOG[language.code]
        assert required <= set(translated)
        assert all(translated[source] != source for source in required)


def test_dmk_inspection_is_translated_in_every_non_english_locale() -> None:
    from diskforge.gui.i18n import CATALOG

    required = {
        "Inspect DMK structure…", "Inspect DMK structure", "DMK files (*.dmk);;All files (*)",
        "Inspecting DMK structure", "DMK structural inspection", "ID address marks", "Tracks",
        "Track length", "Single-density track size", "Ignore density", "Double-density IDAMs",
        "Container bytes",
    }
    for language in LANGUAGES:
        if language.code == "en":
            continue
        translated = CATALOG[language.code]
        assert required <= set(translated)
        assert all(translated[source] != source for source in required)


def test_fat_directory_creation_is_translated_in_every_non_english_locale() -> None:
    from diskforge.gui.i18n import CATALOG

    required = {
        "Create FAT directory…", "Create FAT directory", "New directory name",
        "Creating FAT directory", "Created FAT directory {path}",
    }
    for language in LANGUAGES:
        if language.code == "en":
            continue
        translated = CATALOG[language.code]
        assert required <= set(translated)
        assert all(translated[source] != source for source in required)


def test_fat_regular_file_copy_is_translated_in_every_non_english_locale() -> None:
    from diskforge.gui.i18n import CATALOG

    required = {
        "Copy to directory…", "Copy image file", "Copying image file", "Copy image entry", "Copying image entry", "Copied entry to {path}",
    }
    for language in LANGUAGES:
        if language.code == "en":
            continue
        translated = CATALOG[language.code]
        assert required <= set(translated)
        assert all(translated[source] != source for source in required)


def test_udi_inspector_is_translated_in_every_non_english_locale() -> None:
    from diskforge.gui.i18n import CATALOG

    required = {
        "Inspect UDI structure…", "Inspect UDI structure", "UDI files (*.udi);;All files (*)",
        "Inspecting UDI structure", "UDI structural inspection", "Extended header bytes",
        "Track data bytes", "Clock marks", "CRC32",
    }
    for language in LANGUAGES:
        if language.code == "en":
            continue
        translated = CATALOG[language.code]
        assert required <= set(translated)
        assert all(translated[source] != source for source in required - {"CRC32"})


def test_scp_inspector_is_translated_in_every_non_english_locale() -> None:
    from diskforge.gui.i18n import CATALOG

    required = {
        "Inspect SCP structure…", "Inspect SCP structure", "SCP files (*.scp);;All files (*)",
        "Inspecting SCP structure", "SCP structural inspection", "Revolutions per track", "Resolution",
        "Read-only flux", "No flux decoding or RAW export is available.", "Start track", "End track",
        "Heads", "Flux bytes", "Checksum",
    }
    for language in LANGUAGES:
        if language.code == "en":
            continue
        translated = CATALOG[language.code]
        assert required <= set(translated)
        assert all(translated[source] != source for source in required)


def test_hxc_mfm_inspection_text_is_translated_in_every_non_english_locale() -> None:
    from diskforge.gui.i18n import CATALOG

    required = {
        "Inspect HxC MFM structure…",
        "Inspect HxC MFM structure",
        "HxC MFM files (*.mfm);;All files (*)",
        "Inspecting HxC MFM structure",
        "HxC MFM structural inspection",
        "Bitrate",
        "Interface type",
        "Track table offset",
        "Padding bytes",
    }
    for language in LANGUAGES:
        if language.code == "en":
            continue
        translated = CATALOG[language.code]
        assert required <= set(translated)
        assert all(translated[source] != source for source in required)


def test_fat_batch_delete_text_is_translated_in_every_non_english_locale() -> None:
    from diskforge.gui.i18n import CATALOG

    required = {
        "Delete FAT file or directory tree",
        "Delete one explicit non-root FAT file or directory tree from a writable image. The path is validated before deletion, the recipe previews a write without accessing devices, and a directory tree deletion is irreversible.",
    }
    for language in LANGUAGES:
        if language.code == "en":
            continue
        translated = CATALOG[language.code]
        assert required <= set(translated)
        assert all(translated[source] != source for source in required)


def test_woz2_inspection_is_translated_in_every_non_english_locale() -> None:
    from diskforge.gui.i18n import CATALOG

    required = {
        "Inspect WOZ2 structure…",
        "Inspect WOZ2 structure",
        "WOZ files (*.woz);;All files (*)",
        "Inspecting WOZ2 structure",
        "WOZ2 structural inspection",
        "Bit tracks",
        "Flux tracks",
        "INFO version",
        "Disk type",
        "Creator",
        "CRC checked",
        "Metadata entries",
    }
    for language in LANGUAGES:
        if language.code == "en":
            continue
        translated = CATALOG[language.code]
        assert required <= set(translated)
        assert all(translated[source] != source for source in required)


def test_a2r3_inspection_is_translated_in_every_non_english_locale() -> None:
    from diskforge.gui.i18n import CATALOG

    required = {
        "Inspect A2R3 structure…",
        "Inspect A2R3 structure",
        "A2R files (*.a2r);;All files (*)",
        "Inspecting A2R3 structure",
        "A2R3 structural inspection",
        "Raw captures",
        "Solved flux tracks",
        "Read-only flux",
        "No decoding or RAW export is available.",
        "Drive type",
        "Write protected",
        "Synchronized",
        "Hard sector count",
    }
    for language in LANGUAGES:
        if language.code == "en":
            continue
        translated = CATALOG[language.code]
        assert required <= set(translated)
        assert all(translated[source] != source for source in required)



def test_g64_inspection_is_translated_in_every_non_english_locale() -> None:
    from diskforge.gui.i18n import CATALOG

    required = {
        "Inspect G64 structure…",
        "Inspect G64 structure",
        "G64 files (*.g64);;All files (*)",
        "Inspecting G64 structure",
        "G64 structural inspection",
        "GCR tracks",
        "Track entries",
        "Read-only GCR",
        "No decoding or RAW export is available.",
        "Stored track bytes",
        "Constant-speed tracks",
        "Mapped-speed tracks",
    }
    for language in LANGUAGES:
        if language.code == "en":
            continue
        translated = CATALOG[language.code]
        assert required <= set(translated)
        assert all(translated[source] != source for source in required)



def test_p64_inspection_is_translated_in_every_non_english_locale() -> None:
    from diskforge.gui.i18n import CATALOG

    required = {
        "Inspect P64 structure…",
        "Inspect P64 structure",
        "P64 files (*.p64);;All files (*)",
        "Inspecting P64 structure",
        "P64 structural inspection",
        "NRZI half-tracks",
        "Container chunks",
        "Read-only NRZI",
        "No pulse, GCR, sector decoding or RAW export is available.",
        "P64 flags",
    }
    for language in LANGUAGES:
        if language.code == "en":
            continue
        translated = CATALOG[language.code]
        assert required <= set(translated)
        assert all(translated[source] != source for source in required)



def test_g71_inspection_is_translated_in_every_non_english_locale() -> None:
    from diskforge.gui.i18n import CATALOG

    required = {
        "Inspect G71 structure…",
        "Inspect G71 structure",
        "G71 files (*.g71);;All files (*)",
        "Inspecting G71 structure",
        "G71 structural inspection",
        "Opaque double-sided GCR tracks",
        "Half-track entries",
        "Read-only double-sided GCR",
        "No GCR or sector decoding, RAW export, browse, filesystem session, conversion, repair, or writing is available.",
        "Stored track bytes",
        "Constant-speed tracks",
        "Mapped-speed tracks",
    }
    for language in LANGUAGES:
        if language.code == "en":
            continue
        translated = CATALOG[language.code]
        assert required <= set(translated)
        assert all(translated[source] != source for source in required)
