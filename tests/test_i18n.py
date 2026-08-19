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
        "Sleuth Kit browsing is available only for NTFS and EXT filesystems.",
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
