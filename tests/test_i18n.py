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
        "Move image file",
        "Existing target directory",
        "Moving image file",
        "Moved entry to {path}",
        "Move regular FAT file",
        "Image file to move",
        "FAT target directory",
        "Move one regular file within a writable FAT image to an existing image directory. Existing targets are never overwritten and directory moves are deliberately rejected because they are not atomic.",
        "FAT file move requires a source image, an image file path, and an existing target directory.",
        "FAT file move partition index must be a positive integer.",
    }
    for language in LANGUAGES:
        if language.code == "en":
            continue
        translated = CATALOG[language.code]
        assert required <= set(translated)
        assert all(translated[source] != source for source in required)
