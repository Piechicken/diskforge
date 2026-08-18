"""Runtime localization for DiskForge Qt Widgets.

The catalog deliberately uses source strings as stable keys so dialogs created by
existing workflows can be translated without unsafe monkey-patching.  The manager
also translates controls introduced after a language change and switches layout
direction for Arabic.
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Callable

from PySide6.QtCore import QEvent, QObject, QSettings, Qt
from PySide6.QtGui import QAction
from PySide6.QtWidgets import (
    QApplication, QAbstractButton, QComboBox, QDialog, QGroupBox, QLabel, QLineEdit,
    QMainWindow, QMenu, QMessageBox, QTabWidget, QTableWidget, QTreeWidget, QWidget,
)


@dataclass(frozen=True)
class Language:
    code: str
    native_name: str
    english_name: str
    rtl: bool = False


LANGUAGES: tuple[Language, ...] = (
    Language("en", "English", "English"),
    Language("ar", "العربية", "Arabic", True),
    Language("zh_CN", "简体中文", "Simplified Chinese"),
    Language("fr", "Français", "French"),
    Language("ru", "Русский", "Russian"),
    Language("es", "Español", "Spanish"),
    Language("ja", "日本語", "Japanese"),
)

# English sources are intentionally concise. The runtime safely falls back to the
# original source for diagnostic strings that are not yet suitable for translation.
CATALOG: dict[str, dict[str, str]] = {
    "zh_CN": {
        "&File": "文件(&F)", "&Image": "映像(&I)", "&Tools": "工具(&T)", "&Language": "语言(&L)", "&Help": "帮助(&H)", "Exit": "退出",
        "New image…": "新建映像…", "Open image…": "打开映像…", "Close image": "关闭映像", "Extract selected…": "提取所选内容…", "Inject files…": "注入文件…", "Delete selected": "删除所选内容",
        "Modify selected timestamp…": "修改所选时间戳…", "Up": "向上", "Convert image…": "转换映像…", "Verify SHA-256": "验证 SHA-256", "Export directory listing…": "导出目录清单…", "Print directory listing…": "打印目录清单…",
        "Defragment FAT image…": "整理 FAT 映像…", "Edit boot sector…": "编辑启动扇区…", "Read / write physical drive…": "读取/写入物理驱动器…", "Run batch recipe…": "运行批处理方案…", "Create self-extracting bundle…": "创建自解压包…", "View partitions": "查看分区", "Preferences…": "首选项…", "About DiskForge": "关于 DiskForge",
        "Main tools": "主要工具", "Image explorer": "映像资源管理器", "No image open": "未打开映像", "<b>Location</b>": "<b>位置</b>", "Name": "名称", "Type": "类型", "Size": "大小", "Modified": "修改时间", "Path": "路径", "Image information": "映像信息", "Activity": "活动", "Ready": "就绪", "Cancel": "取消",
        "New image": "新建映像", "FAT image (editable)": "FAT 映像（可编辑）", "Raw/IMG image": "原始/IMG 映像", "ISO9660/Joliet from directory": "从目录创建 ISO9660/Joliet", "Browse…": "浏览…", "Image type": "映像类型", "FAT variant": "FAT 变体", "Volume label": "卷标", "ISO source folder": "ISO 源文件夹", "FAT images can be browsed and modified immediately.": "FAT 映像可立即浏览和修改。", "ISO files are authored from a local directory and are read-only after creation.": "ISO 文件由本地目录创建，创建后为只读。", "Raw images are sparse zero-filled files; format them externally or write sectors manually.": "原始映像是稀疏的零填充文件；请在外部格式化或手动写入扇区。", "FAT images are editable and support file injection, deletion and timestamp changes.": "FAT 映像可编辑，支持文件注入、删除和时间戳修改。",
        "Convert image": "转换映像", "Target format": "目标格式", "Destination": "目标位置", "Allow overwrite": "允许覆盖", "Physical drive operations": "物理驱动器操作", "Required only to write a drive": "仅写入驱动器时需要", "Verify sectors after write": "写入后验证扇区", "Image": "映像", "Type ERASE to write": "输入 ERASE 以写入", "Read selected drive to image…": "读取所选驱动器到映像…", "Write image to selected drive": "将映像写入所选驱动器", "Close": "关闭", "Preferences": "首选项", "Optional qemu-img executable": "可选 qemu-img 可执行文件", "Save": "保存",
        "Operation in progress": "操作进行中", "Wait for the current operation to finish or cancel it.": "请等待当前操作完成或将其取消。", "Operation failed": "操作失败", "See Activity for details.": "请在“活动”中查看详细信息。", "Cannot open image": "无法打开映像", "Select files": "选择文件", "Select one or more files or folders to extract.": "请选择一个或多个要提取的文件或文件夹。", "Missing image": "缺少映像", "Choose a valid image and target device.": "请选择有效的映像和目标设备。", "Confirmation required": "需要确认", "Type ERASE exactly before writing a physical device.": "写入物理设备前必须准确输入 ERASE。",
    },
    "es": {
        "&File": "&Archivo", "&Image": "&Imagen", "&Tools": "&Herramientas", "&Language": "&Idioma", "&Help": "A&yuda", "Exit": "Salir", "New image…": "Nueva imagen…", "Open image…": "Abrir imagen…", "Close image": "Cerrar imagen", "Extract selected…": "Extraer selección…", "Inject files…": "Inyectar archivos…", "Delete selected": "Eliminar selección", "Modify selected timestamp…": "Modificar fecha seleccionada…", "Up": "Subir", "Convert image…": "Convertir imagen…", "Verify SHA-256": "Verificar SHA-256", "Export directory listing…": "Exportar lista de directorio…", "Print directory listing…": "Imprimir lista de directorio…", "Defragment FAT image…": "Desfragmentar imagen FAT…", "Edit boot sector…": "Editar sector de arranque…", "Read / write physical drive…": "Leer / escribir unidad física…", "Run batch recipe…": "Ejecutar receta por lotes…", "Create self-extracting bundle…": "Crear paquete autoextraíble…", "View partitions": "Ver particiones", "Preferences…": "Preferencias…", "About DiskForge": "Acerca de DiskForge", "Main tools": "Herramientas principales", "Image explorer": "Explorador de imágenes", "No image open": "No hay imagen abierta", "<b>Location</b>": "<b>Ubicación</b>", "Name": "Nombre", "Type": "Tipo", "Size": "Tamaño", "Modified": "Modificado", "Path": "Ruta", "Image information": "Información de imagen", "Activity": "Actividad", "Ready": "Listo", "Cancel": "Cancelar", "New image": "Nueva imagen", "Browse…": "Examinar…", "Image type": "Tipo de imagen", "FAT variant": "Variante FAT", "Volume label": "Etiqueta de volumen", "ISO source folder": "Carpeta fuente ISO", "Convert image": "Convertir imagen", "Target format": "Formato de destino", "Destination": "Destino", "Allow overwrite": "Permitir sobrescritura", "Physical drive operations": "Operaciones de unidad física", "Required only to write a drive": "Solo es necesario para escribir una unidad", "Verify sectors after write": "Verificar sectores después de escribir", "Image": "Imagen", "Type ERASE to write": "Escriba ERASE para escribir", "Read selected drive to image…": "Leer unidad seleccionada a imagen…", "Write image to selected drive": "Escribir imagen en la unidad seleccionada", "Close": "Cerrar", "Preferences": "Preferencias", "Optional qemu-img executable": "Ejecutable qemu-img opcional", "Save": "Guardar", "Operation in progress": "Operación en curso", "Wait for the current operation to finish or cancel it.": "Espere a que termine la operación actual o cancélela.", "Operation failed": "Operación fallida", "See Activity for details.": "Consulte Actividad para ver los detalles.", "Cannot open image": "No se puede abrir la imagen", "Select files": "Seleccionar archivos", "Missing image": "Falta imagen", "Confirmation required": "Se requiere confirmación",
    },
    "fr": {
        "&File": "&Fichier", "&Image": "&Image", "&Tools": "Ou&tils", "&Language": "&Langue", "&Help": "Aid&e", "Exit": "Quitter", "New image…": "Nouvelle image…", "Open image…": "Ouvrir une image…", "Close image": "Fermer l’image", "Extract selected…": "Extraire la sélection…", "Inject files…": "Injecter des fichiers…", "Delete selected": "Supprimer la sélection", "Modify selected timestamp…": "Modifier l’horodatage…", "Up": "Monter", "Convert image…": "Convertir l’image…", "Verify SHA-256": "Vérifier SHA-256", "Export directory listing…": "Exporter la liste du dossier…", "Print directory listing…": "Imprimer la liste du dossier…", "Defragment FAT image…": "Défragmenter l’image FAT…", "Edit boot sector…": "Modifier le secteur d’amorçage…", "Read / write physical drive…": "Lire / écrire le disque physique…", "Run batch recipe…": "Exécuter une recette par lot…", "Create self-extracting bundle…": "Créer un paquet auto-extractible…", "View partitions": "Afficher les partitions", "Preferences…": "Préférences…", "About DiskForge": "À propos de DiskForge", "Main tools": "Outils principaux", "Image explorer": "Explorateur d’images", "No image open": "Aucune image ouverte", "<b>Location</b>": "<b>Emplacement</b>", "Name": "Nom", "Type": "Type", "Size": "Taille", "Modified": "Modifié", "Path": "Chemin", "Image information": "Informations sur l’image", "Activity": "Activité", "Ready": "Prêt", "Cancel": "Annuler", "New image": "Nouvelle image", "Browse…": "Parcourir…", "Image type": "Type d’image", "FAT variant": "Variante FAT", "Volume label": "Étiquette de volume", "ISO source folder": "Dossier source ISO", "Convert image": "Convertir l’image", "Target format": "Format cible", "Destination": "Destination", "Allow overwrite": "Autoriser l’écrasement", "Physical drive operations": "Opérations sur disque physique", "Image": "Image", "Close": "Fermer", "Preferences": "Préférences", "Save": "Enregistrer", "Operation in progress": "Opération en cours", "Operation failed": "Échec de l’opération", "Cannot open image": "Impossible d’ouvrir l’image", "Select files": "Sélectionner des fichiers", "Missing image": "Image manquante", "Confirmation required": "Confirmation requise",
    },
    "ru": {
        "&File": "&Файл", "&Image": "&Образ", "&Tools": "&Инструменты", "&Language": "&Язык", "&Help": "&Справка", "Exit": "Выход", "New image…": "Создать образ…", "Open image…": "Открыть образ…", "Close image": "Закрыть образ", "Extract selected…": "Извлечь выбранное…", "Inject files…": "Добавить файлы…", "Delete selected": "Удалить выбранное", "Modify selected timestamp…": "Изменить время…", "Up": "Вверх", "Convert image…": "Преобразовать образ…", "Verify SHA-256": "Проверить SHA-256", "Export directory listing…": "Экспортировать список каталога…", "Print directory listing…": "Печать списка каталога…", "Defragment FAT image…": "Дефрагментировать FAT-образ…", "Edit boot sector…": "Изменить загрузочный сектор…", "Read / write physical drive…": "Чтение / запись физического диска…", "Run batch recipe…": "Запустить пакетный сценарий…", "Create self-extracting bundle…": "Создать самораспаковывающийся пакет…", "View partitions": "Показать разделы", "Preferences…": "Параметры…", "About DiskForge": "О DiskForge", "Main tools": "Основные инструменты", "Image explorer": "Проводник образов", "No image open": "Образ не открыт", "<b>Location</b>": "<b>Расположение</b>", "Name": "Имя", "Type": "Тип", "Size": "Размер", "Modified": "Изменено", "Path": "Путь", "Image information": "Сведения об образе", "Activity": "Журнал", "Ready": "Готово", "Cancel": "Отмена", "New image": "Создать образ", "Browse…": "Обзор…", "Image type": "Тип образа", "FAT variant": "Вариант FAT", "Volume label": "Метка тома", "ISO source folder": "Исходная папка ISO", "Convert image": "Преобразовать образ", "Target format": "Целевой формат", "Destination": "Назначение", "Allow overwrite": "Разрешить перезапись", "Physical drive operations": "Операции с физическим диском", "Image": "Образ", "Close": "Закрыть", "Preferences": "Параметры", "Save": "Сохранить", "Operation in progress": "Операция выполняется", "Operation failed": "Сбой операции", "Cannot open image": "Не удалось открыть образ", "Select files": "Выбрать файлы", "Missing image": "Нет образа", "Confirmation required": "Требуется подтверждение",
    },
    "ar": {
        "&File": "&ملف", "&Image": "&صورة", "&Tools": "أ&دوات", "&Language": "ال&لغة", "&Help": "م&ساعدة", "Exit": "خروج", "New image…": "صورة جديدة…", "Open image…": "فتح صورة…", "Close image": "إغلاق الصورة", "Extract selected…": "استخراج المحدد…", "Inject files…": "إدراج ملفات…", "Delete selected": "حذف المحدد", "Modify selected timestamp…": "تعديل الطابع الزمني…", "Up": "أعلى", "Convert image…": "تحويل الصورة…", "Verify SHA-256": "التحقق من SHA-256", "Export directory listing…": "تصدير قائمة المجلد…", "Print directory listing…": "طباعة قائمة المجلد…", "Defragment FAT image…": "إلغاء تجزئة صورة FAT…", "Edit boot sector…": "تحرير قطاع الإقلاع…", "Read / write physical drive…": "قراءة / كتابة القرص الفعلي…", "Run batch recipe…": "تشغيل وصفة دفعة…", "Create self-extracting bundle…": "إنشاء حزمة ذاتية الاستخراج…", "View partitions": "عرض الأقسام", "Preferences…": "التفضيلات…", "About DiskForge": "حول DiskForge", "Main tools": "الأدوات الرئيسية", "Image explorer": "مستكشف الصور", "No image open": "لا توجد صورة مفتوحة", "<b>Location</b>": "<b>الموقع</b>", "Name": "الاسم", "Type": "النوع", "Size": "الحجم", "Modified": "تم التعديل", "Path": "المسار", "Image information": "معلومات الصورة", "Activity": "النشاط", "Ready": "جاهز", "Cancel": "إلغاء", "New image": "صورة جديدة", "Browse…": "استعراض…", "Image type": "نوع الصورة", "FAT variant": "إصدار FAT", "Volume label": "تسمية وحدة التخزين", "ISO source folder": "مجلد مصدر ISO", "Convert image": "تحويل الصورة", "Target format": "تنسيق الهدف", "Destination": "الوجهة", "Allow overwrite": "السماح بالاستبدال", "Physical drive operations": "عمليات القرص الفعلي", "Image": "الصورة", "Close": "إغلاق", "Preferences": "التفضيلات", "Save": "حفظ", "Operation in progress": "العملية قيد التنفيذ", "Operation failed": "فشلت العملية", "Cannot open image": "تعذر فتح الصورة", "Select files": "اختيار ملفات", "Missing image": "الصورة مفقودة", "Confirmation required": "التأكيد مطلوب",
    },
    "ja": {
        "&File": "ファイル(&F)", "&Image": "イメージ(&I)", "&Tools": "ツール(&T)", "&Language": "言語(&L)", "&Help": "ヘルプ(&H)", "Exit": "終了", "New image…": "新しいイメージ…", "Open image…": "イメージを開く…", "Close image": "イメージを閉じる", "Extract selected…": "選択項目を抽出…", "Inject files…": "ファイルを追加…", "Delete selected": "選択項目を削除", "Modify selected timestamp…": "選択項目の時刻を変更…", "Up": "上へ", "Convert image…": "イメージを変換…", "Verify SHA-256": "SHA-256 を検証", "Export directory listing…": "ディレクトリ一覧を出力…", "Print directory listing…": "ディレクトリ一覧を印刷…", "Defragment FAT image…": "FAT イメージをデフラグ…", "Edit boot sector…": "ブートセクターを編集…", "Read / write physical drive…": "物理ドライブを読み書き…", "Run batch recipe…": "バッチレシピを実行…", "Create self-extracting bundle…": "自己展開バンドルを作成…", "View partitions": "パーティションを表示", "Preferences…": "設定…", "About DiskForge": "DiskForge について", "Main tools": "主要ツール", "Image explorer": "イメージエクスプローラー", "No image open": "イメージが開かれていません", "<b>Location</b>": "<b>場所</b>", "Name": "名前", "Type": "種類", "Size": "サイズ", "Modified": "更新日時", "Path": "パス", "Image information": "イメージ情報", "Activity": "アクティビティ", "Ready": "準備完了", "Cancel": "キャンセル", "New image": "新しいイメージ", "Browse…": "参照…", "Image type": "イメージの種類", "FAT variant": "FAT バリアント", "Volume label": "ボリュームラベル", "ISO source folder": "ISO ソースフォルダー", "Convert image": "イメージを変換", "Target format": "変換先形式", "Destination": "保存先", "Allow overwrite": "上書きを許可", "Physical drive operations": "物理ドライブ操作", "Image": "イメージ", "Close": "閉じる", "Preferences": "設定", "Save": "保存", "Operation in progress": "操作を実行中", "Operation failed": "操作に失敗しました", "Cannot open image": "イメージを開けません", "Select files": "ファイルを選択", "Missing image": "イメージがありません", "Confirmation required": "確認が必要です",
    },
}

# Feature additions after the initial catalog. Keeping these mappings adjacent to
# the catalog preserves the source-string contract used by the runtime manager.
CATALOG["zh_CN"].update({
    "Rename selected…": "重命名所选内容…", "Edit DOS attributes…": "编辑 DOS 属性…",
    "Change volume label…": "更改卷标…", "Edit image comment…": "编辑映像注释…",
    "Resize image…": "调整映像大小…", "Compare image…": "比较映像…",
    "Create secure image bundle…": "创建安全映像包…", "Attributes": "属性",
})
CATALOG["es"].update({
    "Rename selected…": "Renombrar selección…", "Edit DOS attributes…": "Editar atributos DOS…",
    "Change volume label…": "Cambiar etiqueta de volumen…", "Edit image comment…": "Editar comentario de imagen…",
    "Resize image…": "Redimensionar imagen…", "Compare image…": "Comparar imagen…",
    "Create secure image bundle…": "Crear paquete seguro de imágenes…", "Attributes": "Atributos",
})
CATALOG["fr"].update({
    "Rename selected…": "Renommer la sélection…", "Edit DOS attributes…": "Modifier les attributs DOS…",
    "Change volume label…": "Changer l’étiquette du volume…", "Edit image comment…": "Modifier le commentaire de l’image…",
    "Resize image…": "Redimensionner l’image…", "Compare image…": "Comparer l’image…",
    "Create secure image bundle…": "Créer un paquet d’images sécurisé…", "Attributes": "Attributs",
})
CATALOG["ru"].update({
    "Rename selected…": "Переименовать выбранное…", "Edit DOS attributes…": "Изменить атрибуты DOS…",
    "Change volume label…": "Изменить метку тома…", "Edit image comment…": "Изменить комментарий к образу…",
    "Resize image…": "Изменить размер образа…", "Compare image…": "Сравнить образ…",
    "Create secure image bundle…": "Создать защищённый пакет образов…", "Attributes": "Атрибуты",
})
CATALOG["ar"].update({
    "Rename selected…": "إعادة تسمية المحدد…", "Edit DOS attributes…": "تحرير سمات DOS…",
    "Change volume label…": "تغيير تسمية وحدة التخزين…", "Edit image comment…": "تحرير تعليق الصورة…",
    "Resize image…": "تغيير حجم الصورة…", "Compare image…": "مقارنة الصورة…",
    "Create secure image bundle…": "إنشاء حزمة صور آمنة…", "Attributes": "السمات",
})
CATALOG["ja"].update({
    "Rename selected…": "選択項目の名前を変更…", "Edit DOS attributes…": "DOS 属性を編集…",
    "Change volume label…": "ボリュームラベルを変更…", "Edit image comment…": "イメージのコメントを編集…",
    "Resize image…": "イメージのサイズを変更…", "Compare image…": "イメージを比較…",
    "Create secure image bundle…": "安全なイメージバンドルを作成…", "Attributes": "属性",
})

# v0.4 media compatibility and El Torito workflow additions.
CATALOG["zh_CN"].update({
    "Wrap FAT image in MBR…": "将 FAT 映像封装到 MBR 中…", "Trim trailing zero sectors…": "裁剪尾部零扇区…",
    "Inspect / export ISO boot image…": "检查/导出 ISO 启动映像…", "DMF 1.68 MB FAT12 image": "DMF 1.68 MB FAT12 映像",
    "Creates an 80×2×21-sector FAT12 image file. Physical floppy formatting is not performed.": "创建 80×2×21 扇区的 FAT12 映像文件；不执行物理软盘格式化。",
})
CATALOG["es"].update({
    "Wrap FAT image in MBR…": "Envolver imagen FAT en MBR…", "Trim trailing zero sectors…": "Recortar sectores cero finales…",
    "Inspect / export ISO boot image…": "Inspeccionar / exportar imagen de arranque ISO…", "DMF 1.68 MB FAT12 image": "Imagen DMF FAT12 de 1,68 MB",
    "Creates an 80×2×21-sector FAT12 image file. Physical floppy formatting is not performed.": "Crea un archivo de imagen FAT12 de 80×2×21 sectores. No se realiza formateo físico de disquete.",
})
CATALOG["fr"].update({
    "Wrap FAT image in MBR…": "Encapsuler l’image FAT dans un MBR…", "Trim trailing zero sectors…": "Rogner les secteurs zéro finaux…",
    "Inspect / export ISO boot image…": "Inspecter / exporter l’image d’amorçage ISO…", "DMF 1.68 MB FAT12 image": "Image DMF FAT12 de 1,68 Mo",
    "Creates an 80×2×21-sector FAT12 image file. Physical floppy formatting is not performed.": "Crée un fichier image FAT12 de 80×2×21 secteurs. Aucun formatage physique de disquette n’est effectué.",
})
CATALOG["ru"].update({
    "Wrap FAT image in MBR…": "Обернуть FAT-образ в MBR…", "Trim trailing zero sectors…": "Удалить нулевые сектора в конце…",
    "Inspect / export ISO boot image…": "Просмотреть / экспортировать загрузочный образ ISO…", "DMF 1.68 MB FAT12 image": "Образ DMF FAT12 1,68 МБ",
    "Creates an 80×2×21-sector FAT12 image file. Physical floppy formatting is not performed.": "Создаёт файл FAT12 с геометрией 80×2×21 секторов. Физическое форматирование дискеты не выполняется.",
})
CATALOG["ar"].update({
    "Wrap FAT image in MBR…": "تغليف صورة FAT داخل MBR…", "Trim trailing zero sectors…": "اقتطاع القطاعات الصفرية اللاحقة…",
    "Inspect / export ISO boot image…": "فحص / تصدير صورة إقلاع ISO…", "DMF 1.68 MB FAT12 image": "صورة DMF FAT12 بحجم 1.68 ميغابايت",
    "Creates an 80×2×21-sector FAT12 image file. Physical floppy formatting is not performed.": "ينشئ ملف صورة FAT12 بهندسة 80×2×21 قطاعاً. لا يتم إجراء تهيئة فعلية للقرص المرن.",
})
CATALOG["ja"].update({
    "Wrap FAT image in MBR…": "FAT イメージを MBR でラップ…", "Trim trailing zero sectors…": "末尾のゼロセクターをトリミング…",
    "Inspect / export ISO boot image…": "ISO ブートイメージを検査 / エクスポート…", "DMF 1.68 MB FAT12 image": "DMF 1.68 MB FAT12 イメージ",
    "Creates an 80×2×21-sector FAT12 image file. Physical floppy formatting is not performed.": "80×2×21 セクターの FAT12 イメージファイルを作成します。物理フロッピーのフォーマットは行いません。",
})


def _catalog_keys() -> set[str]:
    return {key for translations in CATALOG.values() for key in translations}


TRANSLATABLE = _catalog_keys()


class LanguageManager(QObject):
    """Translate existing and newly shown Qt controls with a persisted locale."""

    def __init__(self, app: QApplication, settings: QSettings) -> None:
        super().__init__(app)
        self.app = app
        self.settings = settings
        requested = str(settings.value("ui_language", "en"))
        self.language = next((item for item in LANGUAGES if item.code == requested), LANGUAGES[0])
        self._applying = False
        app.installEventFilter(self)
        self._apply_direction()

    def text(self, source: str) -> str:
        return CATALOG.get(self.language.code, {}).get(source, source)

    def set_language(self, code: str) -> None:
        target = next((item for item in LANGUAGES if item.code == code), None)
        if target is None:
            return
        self.language = target
        self.settings.setValue("ui_language", code)
        self._apply_direction()
        self.retranslate_all()

    def _apply_direction(self) -> None:
        self.app.setLayoutDirection(Qt.LayoutDirection.RightToLeft if self.language.rtl else Qt.LayoutDirection.LeftToRight)

    def eventFilter(self, watched: QObject, event: QEvent) -> bool:  # type: ignore[override]
        if not self._applying and event.type() in {QEvent.Type.Show, QEvent.Type.PolishRequest} and isinstance(watched, QWidget):
            self.apply_widget(watched)
        return False

    def retranslate_all(self) -> None:
        for widget in self.app.topLevelWidgets():
            self.apply_widget(widget, recursive=True)

    def _apply_text(self, object_: QObject, getter: Callable[[], str], setter: Callable[[str], None], key: str) -> None:
        current = getter()
        source = object_.property(key)
        if source is None:
            if current not in TRANSLATABLE:
                return
            source = current
            object_.setProperty(key, source)
        source = str(source)
        last_rendered = object_.property(f"{key}_rendered")
        # Dynamic content replaces the initial static text; do not overwrite it.
        if last_rendered is not None and current not in {source, str(last_rendered)} and current not in TRANSLATABLE:
            object_.setProperty(key, None)
            object_.setProperty(f"{key}_rendered", None)
            return
        translated = self.text(source)
        if current != translated:
            setter(translated)
        object_.setProperty(f"{key}_rendered", translated)

    def apply_widget(self, widget: QWidget, recursive: bool = True) -> None:
        if self._applying:
            return
        self._applying = True
        try:
            widgets = [widget]
            if recursive:
                widgets.extend(widget.findChildren(QWidget))
            for current in widgets:
                if isinstance(current, (QMainWindow, QDialog, QMessageBox)):
                    self._apply_text(current, current.windowTitle, current.setWindowTitle, "df_source_title")
                if isinstance(current, QMessageBox):
                    self._apply_text(current, current.text, current.setText, "df_source_message")
                if isinstance(current, QLabel):
                    self._apply_text(current, current.text, current.setText, "df_source_text")
                if isinstance(current, QAbstractButton):
                    self._apply_text(current, current.text, current.setText, "df_source_text")
                if isinstance(current, QLineEdit):
                    self._apply_text(current, current.placeholderText, current.setPlaceholderText, "df_source_placeholder")
                if isinstance(current, QComboBox):
                    for index in range(current.count()):
                        property_name = f"df_source_combo_{index}"
                        source = current.property(property_name)
                        if source is None and current.itemText(index) in TRANSLATABLE:
                            source = current.itemText(index)
                            current.setProperty(property_name, source)
                        if source is not None:
                            current.setItemText(index, self.text(str(source)))
                if isinstance(current, QGroupBox):
                    self._apply_text(current, current.title, current.setTitle, "df_source_title")
                if isinstance(current, QMenu):
                    self._apply_text(current, current.title, current.setTitle, "df_source_title")
                if isinstance(current, QTabWidget):
                    for index in range(current.count()):
                        property_name = f"df_source_tab_{index}"
                        source = current.property(property_name)
                        if source is None and current.tabText(index) in TRANSLATABLE:
                            source = current.tabText(index)
                            current.setProperty(property_name, source)
                        if source is not None:
                            current.setTabText(index, self.text(str(source)))
                if isinstance(current, QTreeWidget):
                    labels: list[str] = []
                    for column in range(current.columnCount()):
                        property_name = f"df_source_tree_header_{column}"
                        source = current.property(property_name)
                        visible = current.headerItem().text(column)
                        if source is None and visible in TRANSLATABLE:
                            source = visible
                            current.setProperty(property_name, source)
                        labels.append(self.text(str(source)) if source is not None else visible)
                    current.setHeaderLabels(labels)
                if isinstance(current, QTableWidget):
                    labels: list[str] = []
                    for column in range(current.columnCount()):
                        property_name = f"df_source_table_header_{column}"
                        source = current.property(property_name)
                        visible = current.horizontalHeaderItem(column).text() if current.horizontalHeaderItem(column) else ""
                        if source is None and visible in TRANSLATABLE:
                            source = visible
                            current.setProperty(property_name, source)
                        labels.append(self.text(str(source)) if source is not None else visible)
                    current.setHorizontalHeaderLabels(labels)
                for action in current.actions():
                    self.apply_action(action)
        finally:
            self._applying = False

    def apply_action(self, action: QAction) -> None:
        self._apply_text(action, action.text, action.setText, "df_source_action")


_manager: LanguageManager | None = None


def install_language_manager(app: QApplication, settings: QSettings) -> LanguageManager:
    global _manager
    _manager = LanguageManager(app, settings)
    return _manager


def language_manager() -> LanguageManager:
    if _manager is None:
        raise RuntimeError("LanguageManager has not been installed")
    return _manager
