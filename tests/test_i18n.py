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
