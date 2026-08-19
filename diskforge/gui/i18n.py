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

# v0.5 desktop interaction, appearance and optical-read additions.
CATALOG["zh_CN"].update({
    "Preview selected file": "预览所选文件", "Open recent": "打开最近映像", "No recent images": "没有最近映像", "Clear recent images": "清除最近映像",
    "Details view": "详细信息视图", "Icon view": "图标视图", "Design batch extraction…": "设计批量提取…", "Appearance": "外观", "Light": "浅色", "Midnight": "深色",
    "Read optical media to ISO": "读取光学介质到 ISO", "Read-only optical media": "只读光学介质",
})
CATALOG["es"].update({
    "Preview selected file": "Previsualizar archivo seleccionado", "Open recent": "Abrir recientes", "No recent images": "No hay imágenes recientes", "Clear recent images": "Borrar imágenes recientes",
    "Details view": "Vista de detalles", "Icon view": "Vista de iconos", "Design batch extraction…": "Diseñar extracción por lotes…", "Appearance": "Apariencia", "Light": "Claro", "Midnight": "Medianoche",
    "Read optical media to ISO": "Leer medio óptico a ISO", "Read-only optical media": "Medio óptico de solo lectura",
})
CATALOG["fr"].update({
    "Preview selected file": "Prévisualiser le fichier sélectionné", "Open recent": "Ouvrir les éléments récents", "No recent images": "Aucune image récente", "Clear recent images": "Effacer les images récentes",
    "Details view": "Vue détaillée", "Icon view": "Vue par icônes", "Design batch extraction…": "Concevoir une extraction par lot…", "Appearance": "Apparence", "Light": "Clair", "Midnight": "Minuit",
    "Read optical media to ISO": "Lire le média optique vers ISO", "Read-only optical media": "Média optique en lecture seule",
})
CATALOG["ru"].update({
    "Preview selected file": "Просмотреть выбранный файл", "Open recent": "Открыть недавние", "No recent images": "Нет недавних образов", "Clear recent images": "Очистить недавние образы",
    "Details view": "Подробный вид", "Icon view": "Вид значков", "Design batch extraction…": "Создать пакетное извлечение…", "Appearance": "Оформление", "Light": "Светлое", "Midnight": "Полночь",
    "Read optical media to ISO": "Считать оптический носитель в ISO", "Read-only optical media": "Оптический носитель только для чтения",
})
CATALOG["ar"].update({
    "Preview selected file": "معاينة الملف المحدد", "Open recent": "فتح الأخيرة", "No recent images": "لا توجد صور حديثة", "Clear recent images": "مسح الصور الحديثة",
    "Details view": "عرض التفاصيل", "Icon view": "عرض الأيقونات", "Design batch extraction…": "تصميم استخراج دفعي…", "Appearance": "المظهر", "Light": "فاتح", "Midnight": "ليلي",
    "Read optical media to ISO": "قراءة الوسيط الضوئي إلى ISO", "Read-only optical media": "وسيط ضوئي للقراءة فقط",
})
CATALOG["ja"].update({
    "Preview selected file": "選択ファイルをプレビュー", "Open recent": "最近使った項目を開く", "No recent images": "最近使ったイメージはありません", "Clear recent images": "最近使ったイメージを消去",
    "Details view": "詳細表示", "Icon view": "アイコン表示", "Design batch extraction…": "バッチ抽出を設計…", "Appearance": "外観", "Light": "ライト", "Midnight": "ミッドナイト",
    "Read optical media to ISO": "光学メディアを ISO に読み取る", "Read-only optical media": "読み取り専用の光学メディア",
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

# Convergence additions: deployable FAT media, bootable ISO authoring and original templates.
CATALOG["zh_CN"].update({
    "Prepare FAT deployment image…": "准备 FAT 部署映像…", "Optional ISO boot image": "可选 ISO 启动映像", "Boot media mode": "启动介质模式",
    "No emulation": "无仿真", "Floppy emulation": "软盘仿真", "Hard-disk emulation": "硬盘仿真",
    "Write boot info table into the ISO copy": "在 ISO 副本中写入启动信息表", "Apply original template…": "应用原创模板…",
})
CATALOG["es"].update({
    "Prepare FAT deployment image…": "Preparar imagen FAT para despliegue…", "Optional ISO boot image": "Imagen de arranque ISO opcional", "Boot media mode": "Modo de medio de arranque",
    "No emulation": "Sin emulación", "Floppy emulation": "Emulación de disquete", "Hard-disk emulation": "Emulación de disco duro",
    "Write boot info table into the ISO copy": "Escribir tabla de información de arranque en la copia ISO", "Apply original template…": "Aplicar plantilla original…",
})
CATALOG["fr"].update({
    "Prepare FAT deployment image…": "Préparer l’image FAT de déploiement…", "Optional ISO boot image": "Image d’amorçage ISO facultative", "Boot media mode": "Mode de média d’amorçage",
    "No emulation": "Sans émulation", "Floppy emulation": "Émulation de disquette", "Hard-disk emulation": "Émulation de disque dur",
    "Write boot info table into the ISO copy": "Écrire la table d’informations d’amorçage dans la copie ISO", "Apply original template…": "Appliquer le modèle original…",
})
CATALOG["ru"].update({
    "Prepare FAT deployment image…": "Подготовить FAT-образ для развертывания…", "Optional ISO boot image": "Необязательный загрузочный ISO-образ", "Boot media mode": "Режим загрузочного носителя",
    "No emulation": "Без эмуляции", "Floppy emulation": "Эмуляция дискеты", "Hard-disk emulation": "Эмуляция жесткого диска",
    "Write boot info table into the ISO copy": "Записать таблицу загрузочной информации в копию ISO", "Apply original template…": "Применить оригинальный шаблон…",
})
CATALOG["ar"].update({
    "Prepare FAT deployment image…": "إعداد صورة FAT للنشر…", "Optional ISO boot image": "صورة إقلاع ISO اختيارية", "Boot media mode": "وضع وسيط الإقلاع",
    "No emulation": "بدون محاكاة", "Floppy emulation": "محاكاة القرص المرن", "Hard-disk emulation": "محاكاة القرص الصلب",
    "Write boot info table into the ISO copy": "كتابة جدول معلومات الإقلاع داخل نسخة ISO", "Apply original template…": "تطبيق قالب أصلي…",
})
CATALOG["ja"].update({
    "Prepare FAT deployment image…": "FAT 展開イメージを準備…", "Optional ISO boot image": "任意の ISO ブートイメージ", "Boot media mode": "ブートメディアモード",
    "No emulation": "エミュレーションなし", "Floppy emulation": "フロッピーエミュレーション", "Hard-disk emulation": "ハードディスクエミュレーション",
    "Write boot info table into the ISO copy": "ISO コピーにブート情報テーブルを書き込む", "Apply original template…": "オリジナルテンプレートを適用…",
})
TRANSLATABLE = _catalog_keys()

# Task-center workflow additions.
CATALOG["zh_CN"].update({"Tasks": "任务", "Status": "状态", "Task": "任务", "Detail": "详情", "Clear completed tasks": "清除已完成任务"})
CATALOG["es"].update({"Tasks": "Tareas", "Status": "Estado", "Task": "Tarea", "Detail": "Detalle", "Clear completed tasks": "Limpiar tareas completadas"})
CATALOG["fr"].update({"Tasks": "Tâches", "Status": "État", "Task": "Tâche", "Detail": "Détail", "Clear completed tasks": "Effacer les tâches terminées"})
CATALOG["ru"].update({"Tasks": "Задачи", "Status": "Состояние", "Task": "Задача", "Detail": "Сведения", "Clear completed tasks": "Очистить завершённые задачи"})
CATALOG["ar"].update({"Tasks": "المهام", "Status": "الحالة", "Task": "المهمة", "Detail": "التفاصيل", "Clear completed tasks": "مسح المهام المكتملة"})
CATALOG["ja"].update({"Tasks": "タスク", "Status": "状態", "Task": "タスク", "Detail": "詳細", "Clear completed tasks": "完了したタスクを消去"})
TRANSLATABLE = _catalog_keys()

# Interface accessibility additions.
CATALOG["zh_CN"].update({"Interface font": "界面字体", "Interface font size": "界面字号"})
CATALOG["es"].update({"Interface font": "Fuente de interfaz", "Interface font size": "Tamaño de fuente de interfaz"})
CATALOG["fr"].update({"Interface font": "Police de l’interface", "Interface font size": "Taille de police de l’interface"})
CATALOG["ru"].update({"Interface font": "Шрифт интерфейса", "Interface font size": "Размер шрифта интерфейса"})
CATALOG["ar"].update({"Interface font": "خط الواجهة", "Interface font size": "حجم خط الواجهة"})
CATALOG["ja"].update({"Interface font": "インターフェースフォント", "Interface font size": "インターフェースの文字サイズ"})
TRANSLATABLE = _catalog_keys()

# Legacy-media compatibility and internal-preview UI additions.
CATALOG["zh_CN"].update({
    "DiskForge Workspace": "DiskForge 工作区", "Inspect, shape, validate, and distribute disk images with confidence.": "自信地检查、处理、验证并分发磁盘映像。", "IMAGE STUDIO": "映像工作室",
    "Location": "位置", "Preparing file preview": "正在准备文件预览", "Preview unavailable": "预览不可用", "Preview inspected": "已检查预览",
    "Image preview": "图像预览", "Read-only rendered image preview": "只读渲染图像预览", "Text preview": "文本预览", "Read-only internal text preview": "只读内置文本预览",
    "ZIP archive contents": "ZIP 压缩包内容", "TAR archive contents": "TAR 压缩包内容", "CAB archive contents": "CAB 压缩包内容", "InstallShield setup data": "InstallShield 安装数据",
    "Archive was inspected without extraction": "已检查压缩包，未进行解压", "Cabinet index inspected without extraction": "已检查 CAB 目录，未进行解压", "Legacy InstallShield package structure inspected without execution": "已检查旧式 InstallShield 包结构，未执行任何内容",
    "DOS MZ executable": "DOS MZ 可执行文件", "16-bit Windows NE executable": "16 位 Windows NE 可执行文件", "Windows PE executable": "Windows PE 可执行文件", "Read-only executable structure inspection": "只读可执行文件结构检查",
    "Binary inspection": "二进制检查", "Read-only hexadecimal preview; no system application is required": "只读十六进制预览；无需系统默认应用程序", "GZip text preview": "GZip 文本预览", "GZip file": "GZip 文件", "Microsoft SZDD compressed file": "Microsoft SZDD 压缩文件",
})
CATALOG["es"].update({
    "DiskForge Workspace": "Espacio de trabajo DiskForge", "Inspect, shape, validate, and distribute disk images with confidence.": "Inspeccione, prepare, valide y distribuya imágenes de disco con confianza.", "IMAGE STUDIO": "ESTUDIO DE IMÁGENES",
    "Location": "Ubicación", "Preparing file preview": "Preparando vista previa", "Preview unavailable": "Vista previa no disponible", "Preview inspected": "Vista previa inspeccionada",
    "Image preview": "Vista previa de imagen", "Read-only rendered image preview": "Vista previa de imagen renderizada de solo lectura", "Text preview": "Vista previa de texto", "Read-only internal text preview": "Vista previa de texto interna de solo lectura",
    "ZIP archive contents": "Contenido del archivo ZIP", "TAR archive contents": "Contenido del archivo TAR", "CAB archive contents": "Contenido del archivo CAB", "InstallShield setup data": "Datos de instalación InstallShield",
    "Archive was inspected without extraction": "El archivo se inspeccionó sin extraerlo", "Cabinet index inspected without extraction": "El índice CAB se inspeccionó sin extraerlo", "Legacy InstallShield package structure inspected without execution": "La estructura del paquete InstallShield se inspeccionó sin ejecutarla",
    "DOS MZ executable": "Ejecutable DOS MZ", "16-bit Windows NE executable": "Ejecutable Windows NE de 16 bits", "Windows PE executable": "Ejecutable Windows PE", "Read-only executable structure inspection": "Inspección de estructura ejecutable de solo lectura",
    "Binary inspection": "Inspección binaria", "Read-only hexadecimal preview; no system application is required": "Vista hexadecimal de solo lectura; no se requiere una aplicación del sistema", "GZip text preview": "Vista previa de texto GZip", "GZip file": "Archivo GZip", "Microsoft SZDD compressed file": "Archivo comprimido Microsoft SZDD",
})
CATALOG["fr"].update({
    "DiskForge Workspace": "Espace de travail DiskForge", "Inspect, shape, validate, and distribute disk images with confidence.": "Inspectez, préparez, validez et distribuez des images disque en toute confiance.", "IMAGE STUDIO": "ATELIER D’IMAGES",
    "Location": "Emplacement", "Preparing file preview": "Préparation de l’aperçu", "Preview unavailable": "Aperçu indisponible", "Preview inspected": "Aperçu inspecté",
    "Image preview": "Aperçu d’image", "Read-only rendered image preview": "Aperçu d’image rendue en lecture seule", "Text preview": "Aperçu de texte", "Read-only internal text preview": "Aperçu de texte interne en lecture seule",
    "ZIP archive contents": "Contenu de l’archive ZIP", "TAR archive contents": "Contenu de l’archive TAR", "CAB archive contents": "Contenu de l’archive CAB", "InstallShield setup data": "Données d’installation InstallShield",
    "Archive was inspected without extraction": "L’archive a été inspectée sans extraction", "Cabinet index inspected without extraction": "L’index CAB a été inspecté sans extraction", "Legacy InstallShield package structure inspected without execution": "La structure du paquet InstallShield a été inspectée sans exécution",
    "DOS MZ executable": "Exécutable DOS MZ", "16-bit Windows NE executable": "Exécutable Windows NE 16 bits", "Windows PE executable": "Exécutable Windows PE", "Read-only executable structure inspection": "Inspection de structure exécutable en lecture seule",
    "Binary inspection": "Inspection binaire", "Read-only hexadecimal preview; no system application is required": "Aperçu hexadécimal en lecture seule ; aucune application système requise", "GZip text preview": "Aperçu texte GZip", "GZip file": "Fichier GZip", "Microsoft SZDD compressed file": "Fichier compressé Microsoft SZDD",
})
CATALOG["ru"].update({
    "DiskForge Workspace": "Рабочее пространство DiskForge", "Inspect, shape, validate, and distribute disk images with confidence.": "Уверенно проверяйте, подготавливайте, подтверждайте и распространяйте образы дисков.", "IMAGE STUDIO": "СТУДИЯ ОБРАЗОВ",
    "Location": "Расположение", "Preparing file preview": "Подготовка предпросмотра", "Preview unavailable": "Предпросмотр недоступен", "Preview inspected": "Предпросмотр проверен",
    "Image preview": "Предпросмотр изображения", "Read-only rendered image preview": "Предпросмотр отрисованного изображения только для чтения", "Text preview": "Предпросмотр текста", "Read-only internal text preview": "Встроенный предпросмотр текста только для чтения",
    "ZIP archive contents": "Содержимое ZIP-архива", "TAR archive contents": "Содержимое TAR-архива", "CAB archive contents": "Содержимое CAB-архива", "InstallShield setup data": "Данные установки InstallShield",
    "Archive was inspected without extraction": "Архив проверен без извлечения", "Cabinet index inspected without extraction": "Индекс CAB проверен без извлечения", "Legacy InstallShield package structure inspected without execution": "Структура старого пакета InstallShield проверена без выполнения",
    "DOS MZ executable": "Исполняемый файл DOS MZ", "16-bit Windows NE executable": "16-разрядный исполняемый файл Windows NE", "Windows PE executable": "Исполняемый файл Windows PE", "Read-only executable structure inspection": "Проверка структуры исполняемого файла только для чтения",
    "Binary inspection": "Проверка двоичных данных", "Read-only hexadecimal preview; no system application is required": "Шестнадцатеричный предпросмотр только для чтения; системное приложение не требуется", "GZip text preview": "Предпросмотр текста GZip", "GZip file": "Файл GZip", "Microsoft SZDD compressed file": "Сжатый файл Microsoft SZDD",
})
CATALOG["ar"].update({
    "DiskForge Workspace": "مساحة عمل DiskForge", "Inspect, shape, validate, and distribute disk images with confidence.": "افحص صور الأقراص وشكّلها وتحقق منها ووزعها بثقة.", "IMAGE STUDIO": "استوديو الصور",
    "Location": "الموقع", "Preparing file preview": "جارٍ تحضير المعاينة", "Preview unavailable": "المعاينة غير متاحة", "Preview inspected": "تم فحص المعاينة",
    "Image preview": "معاينة الصورة", "Read-only rendered image preview": "معاينة صورة معروضة للقراءة فقط", "Text preview": "معاينة النص", "Read-only internal text preview": "معاينة نصية داخلية للقراءة فقط",
    "ZIP archive contents": "محتويات أرشيف ZIP", "TAR archive contents": "محتويات أرشيف TAR", "CAB archive contents": "محتويات أرشيف CAB", "InstallShield setup data": "بيانات تثبيت InstallShield",
    "Archive was inspected without extraction": "تم فحص الأرشيف دون استخراجه", "Cabinet index inspected without extraction": "تم فحص فهرس CAB دون استخراج", "Legacy InstallShield package structure inspected without execution": "تم فحص بنية حزمة InstallShield القديمة دون تنفيذ",
    "DOS MZ executable": "ملف DOS MZ تنفيذي", "16-bit Windows NE executable": "ملف Windows NE تنفيذي 16 بت", "Windows PE executable": "ملف Windows PE تنفيذي", "Read-only executable structure inspection": "فحص بنية الملف التنفيذي للقراءة فقط",
    "Binary inspection": "فحص ثنائي", "Read-only hexadecimal preview; no system application is required": "معاينة سداسية عشرية للقراءة فقط؛ لا يلزم تطبيق نظام", "GZip text preview": "معاينة نص GZip", "GZip file": "ملف GZip", "Microsoft SZDD compressed file": "ملف Microsoft SZDD مضغوط",
})
CATALOG["ja"].update({
    "DiskForge Workspace": "DiskForge ワークスペース", "Inspect, shape, validate, and distribute disk images with confidence.": "ディスクイメージを確実に検査、編集、検証、配布します。", "IMAGE STUDIO": "イメージスタジオ",
    "Location": "場所", "Preparing file preview": "ファイルプレビューを準備中", "Preview unavailable": "プレビューを利用できません", "Preview inspected": "プレビューを検査しました",
    "Image preview": "画像プレビュー", "Read-only rendered image preview": "読み取り専用の描画済み画像プレビュー", "Text preview": "テキストプレビュー", "Read-only internal text preview": "読み取り専用の内部テキストプレビュー",
    "ZIP archive contents": "ZIP アーカイブの内容", "TAR archive contents": "TAR アーカイブの内容", "CAB archive contents": "CAB アーカイブの内容", "InstallShield setup data": "InstallShield セットアップデータ",
    "Archive was inspected without extraction": "展開せずにアーカイブを検査しました", "Cabinet index inspected without extraction": "展開せずに CAB インデックスを検査しました", "Legacy InstallShield package structure inspected without execution": "実行せずに旧式 InstallShield パッケージ構造を検査しました",
    "DOS MZ executable": "DOS MZ 実行ファイル", "16-bit Windows NE executable": "16 ビット Windows NE 実行ファイル", "Windows PE executable": "Windows PE 実行ファイル", "Read-only executable structure inspection": "読み取り専用の実行ファイル構造検査",
    "Binary inspection": "バイナリ検査", "Read-only hexadecimal preview; no system application is required": "読み取り専用の16進プレビュー。システム既定アプリは不要です", "GZip text preview": "GZip テキストプレビュー", "GZip file": "GZip ファイル", "Microsoft SZDD compressed file": "Microsoft SZDD 圧縮ファイル",
})
TRANSLATABLE = _catalog_keys()

# v0.7.5 route-recovery and visual-workflow additions.
CATALOG["zh_CN"].update({
    "Sleuth Kit browsing is available only for NTFS and EXT filesystems.": "Sleuth Kit 只读浏览仅适用于 NTFS 和 EXT 文件系统。",
    "The current image has no browsable filesystem.": "当前映像没有可浏览的文件系统。",
    "The current image format can be inspected but has no file-level browser.": "当前映像格式可以检查，但没有文件级浏览器。",
    "Batch workflow designer": "批处理工作流设计器", "Design batch workflow…": "设计批处理工作流…", "Edit batch recipe…": "编辑批处理方案…",
    "Batch workflow results": "批处理工作流结果", "Add operation": "添加操作", "Update selected": "更新所选项", "Remove selected": "移除所选项",
    "Move up": "上移", "Move down": "下移", "Operation": "操作", "Operation name": "操作名称", "Source image / bundle": "源映像/容器",
    "Destination image / folder": "目标映像/文件夹", "Succeeded": "成功", "Failed": "失败", "Detail": "详情",
})
CATALOG["es"].update({
    "Sleuth Kit browsing is available only for NTFS and EXT filesystems.": "La exploración de Sleuth Kit solo está disponible para sistemas de archivos NTFS y EXT.",
    "The current image has no browsable filesystem.": "La imagen actual no tiene un sistema de archivos explorable.",
    "The current image format can be inspected but has no file-level browser.": "El formato de imagen actual se puede inspeccionar, pero no tiene explorador de archivos.",
    "Batch workflow designer": "Diseñador de flujo por lotes", "Design batch workflow…": "Diseñar flujo por lotes…", "Edit batch recipe…": "Editar receta por lotes…",
    "Batch workflow results": "Resultados del flujo por lotes", "Add operation": "Añadir operación", "Update selected": "Actualizar selección", "Remove selected": "Eliminar selección",
    "Move up": "Subir", "Move down": "Bajar", "Operation": "Operación", "Operation name": "Nombre de la operación", "Source image / bundle": "Imagen o contenedor de origen",
    "Destination image / folder": "Imagen o carpeta de destino", "Succeeded": "Correcto", "Failed": "Fallido", "Detail": "Detalle",
})
CATALOG["fr"].update({
    "Sleuth Kit browsing is available only for NTFS and EXT filesystems.": "La navigation Sleuth Kit est disponible uniquement pour les systèmes de fichiers NTFS et EXT.",
    "The current image has no browsable filesystem.": "L’image actuelle ne contient aucun système de fichiers navigable.",
    "The current image format can be inspected but has no file-level browser.": "Le format de l’image actuelle peut être inspecté, mais ne dispose pas d’un explorateur de fichiers.",
    "Batch workflow designer": "Concepteur de flux par lot", "Design batch workflow…": "Concevoir un flux par lot…", "Edit batch recipe…": "Modifier une recette par lot…",
    "Batch workflow results": "Résultats du flux par lot", "Add operation": "Ajouter une opération", "Update selected": "Mettre à jour la sélection", "Remove selected": "Supprimer la sélection",
    "Move up": "Monter", "Move down": "Descendre", "Operation": "Opération", "Operation name": "Nom de l’opération", "Source image / bundle": "Image ou conteneur source",
    "Destination image / folder": "Image ou dossier de destination", "Succeeded": "Réussi", "Failed": "Échoué", "Detail": "Détail",
})
CATALOG["ru"].update({
    "Sleuth Kit browsing is available only for NTFS and EXT filesystems.": "Просмотр через Sleuth Kit доступен только для файловых систем NTFS и EXT.",
    "The current image has no browsable filesystem.": "В текущем образе нет доступной для просмотра файловой системы.",
    "The current image format can be inspected but has no file-level browser.": "Текущий формат образа можно проверить, но файловый просмотр недоступен.",
    "Batch workflow designer": "Конструктор пакетного процесса", "Design batch workflow…": "Создать пакетный процесс…", "Edit batch recipe…": "Изменить пакетный сценарий…",
    "Batch workflow results": "Результаты пакетного процесса", "Add operation": "Добавить операцию", "Update selected": "Обновить выбранное", "Remove selected": "Удалить выбранное",
    "Move up": "Переместить выше", "Move down": "Переместить ниже", "Operation": "Операция", "Operation name": "Название операции", "Source image / bundle": "Исходный образ/контейнер",
    "Destination image / folder": "Целевой образ/папка", "Succeeded": "Успешно", "Failed": "Ошибка", "Detail": "Подробности",
})
CATALOG["ar"].update({
    "Sleuth Kit browsing is available only for NTFS and EXT filesystems.": "يتوفر الاستعراض عبر Sleuth Kit لأنظمة الملفات NTFS وEXT فقط.",
    "The current image has no browsable filesystem.": "لا تحتوي الصورة الحالية على نظام ملفات قابل للتصفح.",
    "The current image format can be inspected but has no file-level browser.": "يمكن فحص تنسيق الصورة الحالية، لكنه لا يوفر مستعرض ملفات.",
    "Batch workflow designer": "مصمم سير العمل الدفعي", "Design batch workflow…": "تصميم سير عمل دفعي…", "Edit batch recipe…": "تحرير وصفة الدفعة…",
    "Batch workflow results": "نتائج سير العمل الدفعي", "Add operation": "إضافة عملية", "Update selected": "تحديث المحدد", "Remove selected": "إزالة المحدد",
    "Move up": "نقل لأعلى", "Move down": "نقل لأسفل", "Operation": "العملية", "Operation name": "اسم العملية", "Source image / bundle": "صورة/حاوية المصدر",
    "Destination image / folder": "صورة/مجلد الوجهة", "Succeeded": "نجح", "Failed": "فشل", "Detail": "التفاصيل",
})
CATALOG["ja"].update({
    "Sleuth Kit browsing is available only for NTFS and EXT filesystems.": "Sleuth Kit による閲覧は NTFS と EXT ファイルシステムでのみ利用できます。",
    "The current image has no browsable filesystem.": "現在のイメージには閲覧可能なファイルシステムがありません。",
    "The current image format can be inspected but has no file-level browser.": "現在のイメージ形式は検査できますが、ファイルレベルのブラウザーはありません。",
    "Batch workflow designer": "バッチワークフローデザイナー", "Design batch workflow…": "バッチワークフローを設計…", "Edit batch recipe…": "バッチレシピを編集…",
    "Batch workflow results": "バッチワークフローの結果", "Add operation": "操作を追加", "Update selected": "選択項目を更新", "Remove selected": "選択項目を削除",
    "Move up": "上へ移動", "Move down": "下へ移動", "Operation": "操作", "Operation name": "操作名", "Source image / bundle": "ソースイメージ/コンテナー",
    "Destination image / folder": "出力イメージ/フォルダー", "Succeeded": "成功", "Failed": "失敗", "Detail": "詳細",
})
TRANSLATABLE = _catalog_keys()

# Concise, user-facing about dialog copy.
CATALOG["zh_CN"].update({
    "DiskForge is a cross-platform workspace for opening, editing, checking and distributing disk images.": "DiskForge 是用于打开、编辑、检查和分发磁盘映像的跨平台工作区。",
    "Work with FAT, ISO, RAW and virtual-disk images through explicit, safe workflows. Optional converters and read-only adapters are shown only when configured.": "通过明确、安全的工作流处理 FAT、ISO、RAW 和虚拟磁盘映像。可选转换器与只读适配器仅在已配置时显示。",
})
CATALOG["es"].update({
    "DiskForge is a cross-platform workspace for opening, editing, checking and distributing disk images.": "DiskForge es un espacio de trabajo multiplataforma para abrir, editar, comprobar y distribuir imágenes de disco.",
    "Work with FAT, ISO, RAW and virtual-disk images through explicit, safe workflows. Optional converters and read-only adapters are shown only when configured.": "Trabaje con imágenes FAT, ISO, RAW y de disco virtual mediante flujos explícitos y seguros. Los conversores y adaptadores de solo lectura opcionales solo se muestran cuando están configurados.",
})
CATALOG["fr"].update({
    "DiskForge is a cross-platform workspace for opening, editing, checking and distributing disk images.": "DiskForge est un espace de travail multiplateforme pour ouvrir, modifier, vérifier et distribuer des images disque.",
    "Work with FAT, ISO, RAW and virtual-disk images through explicit, safe workflows. Optional converters and read-only adapters are shown only when configured.": "Travaillez avec des images FAT, ISO, RAW et de disque virtuel au moyen de flux explicites et sûrs. Les convertisseurs et adaptateurs en lecture seule facultatifs ne sont affichés que lorsqu’ils sont configurés.",
})
CATALOG["ru"].update({
    "DiskForge is a cross-platform workspace for opening, editing, checking and distributing disk images.": "DiskForge — кроссплатформенное рабочее пространство для открытия, редактирования, проверки и распространения образов дисков.",
    "Work with FAT, ISO, RAW and virtual-disk images through explicit, safe workflows. Optional converters and read-only adapters are shown only when configured.": "Работайте с образами FAT, ISO, RAW и виртуальных дисков через явные безопасные процессы. Необязательные преобразователи и адаптеры только для чтения отображаются лишь после настройки.",
})
CATALOG["ar"].update({
    "DiskForge is a cross-platform workspace for opening, editing, checking and distributing disk images.": "DiskForge مساحة عمل متعددة المنصات لفتح صور الأقراص وتحريرها وفحصها وتوزيعها.",
    "Work with FAT, ISO, RAW and virtual-disk images through explicit, safe workflows. Optional converters and read-only adapters are shown only when configured.": "اعمل مع صور FAT وISO وRAW والأقراص الافتراضية عبر سير عمل واضح وآمن. لا تظهر المحولات والملحقات الاختيارية للقراءة فقط إلا بعد إعدادها.",
})
CATALOG["ja"].update({
    "DiskForge is a cross-platform workspace for opening, editing, checking and distributing disk images.": "DiskForge はディスクイメージを開く、編集する、検査する、配布するためのクロスプラットフォーム作業領域です。",
    "Work with FAT, ISO, RAW and virtual-disk images through explicit, safe workflows. Optional converters and read-only adapters are shown only when configured.": "FAT、ISO、RAW、仮想ディスクイメージを明示的で安全なワークフローで扱います。任意の変換器と読み取り専用アダプターは設定済みの場合にのみ表示されます。",
})
TRANSLATABLE = _catalog_keys()

# Document workspace controls.
CATALOG["zh_CN"].update({
    "Find in document": "在文档中查找", "Find next": "查找下一个", "Save copy…": "另存为…", "Save back to image": "保存回映像",
    "Unsaved changes": "未保存的更改", "Safe read-only preview": "安全只读预览", "Saving edited text back to the image…": "正在将编辑后的文本保存回映像…",
    "Document details": "文档详情", "Mode:": "模式：", "Editable plain-text content": "可编辑纯文本内容", "Read-only safe inspection": "安全只读检查",
    "No additional metadata.": "没有其他元数据。", "Save edited copy": "保存编辑后的副本", "Save unavailable": "无法保存",
    "Only files in a writable FAT image can be saved back to the image.": "只有可写 FAT 映像中的文件可以保存回映像。",
    "Text editor": "文本编辑器", "Rich Text source editor": "富文本源编辑器", "Markup source editor": "标记源编辑器", "Office document preview": "办公文档预览",
    "Editable text: save a copy or write back to a writable FAT image.": "可编辑文本：可另存副本或写回可写 FAT 映像。",
})
CATALOG["es"].update({
    "Find in document": "Buscar en el documento", "Find next": "Buscar siguiente", "Save copy…": "Guardar copia…", "Save back to image": "Guardar en la imagen",
    "Unsaved changes": "Cambios sin guardar", "Safe read-only preview": "Vista previa segura de solo lectura", "Saving edited text back to the image…": "Guardando el texto editado en la imagen…",
    "Document details": "Detalles del documento", "Mode:": "Modo:", "Editable plain-text content": "Contenido de texto sin formato editable", "Read-only safe inspection": "Inspección segura de solo lectura",
    "No additional metadata.": "No hay metadatos adicionales.", "Save edited copy": "Guardar copia editada", "Save unavailable": "Guardado no disponible",
    "Only files in a writable FAT image can be saved back to the image.": "Solo los archivos de una imagen FAT escribible se pueden guardar en la imagen.",
    "Text editor": "Editor de texto", "Rich Text source editor": "Editor de origen de texto enriquecido", "Markup source editor": "Editor de origen de marcado", "Office document preview": "Vista previa de documento de oficina",
    "Editable text: save a copy or write back to a writable FAT image.": "Texto editable: guarde una copia o escríbalo en una imagen FAT escribible.",
})
CATALOG["fr"].update({
    "Find in document": "Rechercher dans le document", "Find next": "Rechercher le suivant", "Save copy…": "Enregistrer une copie…", "Save back to image": "Enregistrer dans l’image",
    "Unsaved changes": "Modifications non enregistrées", "Safe read-only preview": "Aperçu sûr en lecture seule", "Saving edited text back to the image…": "Enregistrement du texte modifié dans l’image…",
    "Document details": "Détails du document", "Mode:": "Mode :", "Editable plain-text content": "Contenu texte brut modifiable", "Read-only safe inspection": "Inspection sûre en lecture seule",
    "No additional metadata.": "Aucune métadonnée supplémentaire.", "Save edited copy": "Enregistrer la copie modifiée", "Save unavailable": "Enregistrement indisponible",
    "Only files in a writable FAT image can be saved back to the image.": "Seuls les fichiers d’une image FAT inscriptible peuvent être enregistrés dans l’image.",
    "Text editor": "Éditeur de texte", "Rich Text source editor": "Éditeur de source texte enrichi", "Markup source editor": "Éditeur de source de balisage", "Office document preview": "Aperçu de document bureautique",
    "Editable text: save a copy or write back to a writable FAT image.": "Texte modifiable : enregistrez une copie ou réécrivez-le dans une image FAT inscriptible.",
})
CATALOG["ru"].update({
    "Find in document": "Найти в документе", "Find next": "Найти далее", "Save copy…": "Сохранить копию…", "Save back to image": "Сохранить в образ",
    "Unsaved changes": "Несохранённые изменения", "Safe read-only preview": "Безопасный просмотр только для чтения", "Saving edited text back to the image…": "Сохранение изменённого текста в образ…",
    "Document details": "Сведения о документе", "Mode:": "Режим:", "Editable plain-text content": "Редактируемое содержимое обычного текста", "Read-only safe inspection": "Безопасная проверка только для чтения",
    "No additional metadata.": "Дополнительные метаданные отсутствуют.", "Save edited copy": "Сохранить изменённую копию", "Save unavailable": "Сохранение недоступно",
    "Only files in a writable FAT image can be saved back to the image.": "В образ можно сохранить только файлы из доступного для записи FAT-образа.",
    "Text editor": "Текстовый редактор", "Rich Text source editor": "Редактор исходного форматированного текста", "Markup source editor": "Редактор исходной разметки", "Office document preview": "Просмотр офисного документа",
    "Editable text: save a copy or write back to a writable FAT image.": "Редактируемый текст: сохраните копию или запишите его обратно в доступный для записи FAT-образ.",
})
CATALOG["ar"].update({
    "Find in document": "بحث في المستند", "Find next": "بحث عن التالي", "Save copy…": "حفظ نسخة…", "Save back to image": "حفظ في الصورة",
    "Unsaved changes": "تغييرات غير محفوظة", "Safe read-only preview": "معاينة آمنة للقراءة فقط", "Saving edited text back to the image…": "جارٍ حفظ النص المحرر في الصورة…",
    "Document details": "تفاصيل المستند", "Mode:": "الوضع:", "Editable plain-text content": "محتوى نص عادي قابل للتحرير", "Read-only safe inspection": "فحص آمن للقراءة فقط",
    "No additional metadata.": "لا توجد بيانات وصفية إضافية.", "Save edited copy": "حفظ النسخة المحررة", "Save unavailable": "الحفظ غير متاح",
    "Only files in a writable FAT image can be saved back to the image.": "لا يمكن حفظ الملفات في الصورة إلا من صورة FAT قابلة للكتابة.",
    "Text editor": "محرر النص", "Rich Text source editor": "محرر مصدر النص المنسق", "Markup source editor": "محرر مصدر الترميز", "Office document preview": "معاينة مستند مكتبي",
    "Editable text: save a copy or write back to a writable FAT image.": "نص قابل للتحرير: احفظ نسخة أو اكتب النص في صورة FAT قابلة للكتابة.",
})
CATALOG["ja"].update({
    "Find in document": "文書内を検索", "Find next": "次を検索", "Save copy…": "コピーを保存…", "Save back to image": "イメージに保存",
    "Unsaved changes": "未保存の変更", "Safe read-only preview": "安全な読み取り専用プレビュー", "Saving edited text back to the image…": "編集したテキストをイメージに保存しています…",
    "Document details": "文書の詳細", "Mode:": "モード：", "Editable plain-text content": "編集可能なプレーンテキスト", "Read-only safe inspection": "安全な読み取り専用検査",
    "No additional metadata.": "追加のメタデータはありません。", "Save edited copy": "編集したコピーを保存", "Save unavailable": "保存できません",
    "Only files in a writable FAT image can be saved back to the image.": "書き込み可能な FAT イメージ内のファイルのみ、イメージに保存できます。",
    "Text editor": "テキストエディター", "Rich Text source editor": "リッチテキストソースエディター", "Markup source editor": "マークアップソースエディター", "Office document preview": "Office 文書プレビュー",
    "Editable text: save a copy or write back to a writable FAT image.": "編集可能なテキストです。コピーを保存するか、書き込み可能な FAT イメージに書き戻せます。",
})
TRANSLATABLE = _catalog_keys()

# v0.8.0 template-derived FAT layout workflow.
CATALOG["zh_CN"].update({
    "FAT image from template layout": "从模板布局创建 FAT 映像", "FAT layout template": "FAT 布局模板",
    "Reads a valid FAT BPB layout from a template image and creates a new editable image; the template is never modified.": "从模板映像读取有效的 FAT BPB 布局并创建新的可编辑映像；不会修改模板。",
    "Choose FAT layout template": "选择 FAT 布局模板", "FAT template required": "需要 FAT 模板",
    "Choose a valid FAT image template before creating a layout-based image.": "请先选择有效的 FAT 映像模板，再创建基于布局的映像。",
    "Invalid FAT template": "无效的 FAT 模板", "Creating FAT image from template layout": "正在从模板布局创建 FAT 映像",
})
CATALOG["es"].update({
    "FAT image from template layout": "Imagen FAT desde diseño de plantilla", "FAT layout template": "Plantilla de diseño FAT",
    "Reads a valid FAT BPB layout from a template image and creates a new editable image; the template is never modified.": "Lee un diseño BPB FAT válido de una imagen de plantilla y crea una nueva imagen editable; la plantilla nunca se modifica.",
    "Choose FAT layout template": "Elegir plantilla de diseño FAT", "FAT template required": "Se requiere una plantilla FAT",
    "Choose a valid FAT image template before creating a layout-based image.": "Elija una plantilla de imagen FAT válida antes de crear una imagen basada en diseño.",
    "Invalid FAT template": "Plantilla FAT no válida", "Creating FAT image from template layout": "Creando imagen FAT desde el diseño de plantilla",
})
CATALOG["fr"].update({
    "FAT image from template layout": "Image FAT à partir d’une disposition modèle", "FAT layout template": "Modèle de disposition FAT",
    "Reads a valid FAT BPB layout from a template image and creates a new editable image; the template is never modified.": "Lit une disposition BPB FAT valide dans une image modèle et crée une nouvelle image modifiable ; le modèle n’est jamais modifié.",
    "Choose FAT layout template": "Choisir un modèle de disposition FAT", "FAT template required": "Un modèle FAT est requis",
    "Choose a valid FAT image template before creating a layout-based image.": "Choisissez un modèle d’image FAT valide avant de créer une image fondée sur une disposition.",
    "Invalid FAT template": "Modèle FAT non valide", "Creating FAT image from template layout": "Création d’une image FAT à partir de la disposition modèle",
})
CATALOG["ru"].update({
    "FAT image from template layout": "FAT-образ по шаблону разметки", "FAT layout template": "Шаблон разметки FAT",
    "Reads a valid FAT BPB layout from a template image and creates a new editable image; the template is never modified.": "Считывает корректную разметку FAT BPB из образа-шаблона и создаёт новый редактируемый образ; шаблон не изменяется.",
    "Choose FAT layout template": "Выбрать шаблон разметки FAT", "FAT template required": "Требуется шаблон FAT",
    "Choose a valid FAT image template before creating a layout-based image.": "Перед созданием образа по разметке выберите корректный шаблон FAT.",
    "Invalid FAT template": "Некорректный шаблон FAT", "Creating FAT image from template layout": "Создание FAT-образа по шаблону разметки",
})
CATALOG["ar"].update({
    "FAT image from template layout": "صورة FAT من تخطيط قالب", "FAT layout template": "قالب تخطيط FAT",
    "Reads a valid FAT BPB layout from a template image and creates a new editable image; the template is never modified.": "يقرأ تخطيط FAT BPB صالحاً من صورة قالب وينشئ صورة جديدة قابلة للتحرير؛ ولا يعدل القالب أبداً.",
    "Choose FAT layout template": "اختر قالب تخطيط FAT", "FAT template required": "يلزم قالب FAT",
    "Choose a valid FAT image template before creating a layout-based image.": "اختر قالب صورة FAT صالحاً قبل إنشاء صورة تعتمد على التخطيط.",
    "Invalid FAT template": "قالب FAT غير صالح", "Creating FAT image from template layout": "جارٍ إنشاء صورة FAT من تخطيط القالب",
})
CATALOG["ja"].update({
    "FAT image from template layout": "テンプレートレイアウトから FAT イメージを作成", "FAT layout template": "FAT レイアウトテンプレート",
    "Reads a valid FAT BPB layout from a template image and creates a new editable image; the template is never modified.": "テンプレートイメージから有効な FAT BPB レイアウトを読み取り、新しい編集可能なイメージを作成します。テンプレートは変更されません。",
    "Choose FAT layout template": "FAT レイアウトテンプレートを選択", "FAT template required": "FAT テンプレートが必要です",
    "Choose a valid FAT image template before creating a layout-based image.": "レイアウトベースのイメージを作成する前に、有効な FAT イメージテンプレートを選択してください。",
    "Invalid FAT template": "無効な FAT テンプレート", "Creating FAT image from template layout": "テンプレートレイアウトから FAT イメージを作成中",
})
TRANSLATABLE = _catalog_keys()

# v0.8.0 safe boot-code import workflow.
CATALOG["zh_CN"].update({
    "Import boot code safely…": "安全导入启动代码…", "Import boot-sector file": "导入启动扇区文件",
    "Import boot code safely": "安全导入启动代码",
    "The file must be a signed 512-byte boot sector. Only its executable boot-code area will be imported; the current FAT BPB is preserved and a complete image backup is created first. Continue?": "该文件必须是带有效签名的 512 字节启动扇区。只会导入其可执行启动代码区域；将保留当前 FAT BPB，并先创建完整映像备份。是否继续？",
    "Boot code imported": "启动代码已导入", "Boot code imported safely. Backup created:": "启动代码已安全导入。已创建备份：", "Unable to import boot code": "无法导入启动代码",
})
CATALOG["es"].update({
    "Import boot code safely…": "Importar código de arranque de forma segura…", "Import boot-sector file": "Importar archivo de sector de arranque",
    "Import boot code safely": "Importar código de arranque de forma segura",
    "The file must be a signed 512-byte boot sector. Only its executable boot-code area will be imported; the current FAT BPB is preserved and a complete image backup is created first. Continue?": "El archivo debe ser un sector de arranque firmado de 512 bytes. Solo se importará su área de código ejecutable; se conserva el BPB FAT actual y primero se crea una copia de seguridad completa de la imagen. ¿Continuar?",
    "Boot code imported": "Código de arranque importado", "Boot code imported safely. Backup created:": "El código de arranque se importó de forma segura. Copia de seguridad creada:", "Unable to import boot code": "No se puede importar el código de arranque",
})
CATALOG["fr"].update({
    "Import boot code safely…": "Importer le code d’amorçage en toute sécurité…", "Import boot-sector file": "Importer un fichier de secteur d’amorçage",
    "Import boot code safely": "Importer le code d’amorçage en toute sécurité",
    "The file must be a signed 512-byte boot sector. Only its executable boot-code area will be imported; the current FAT BPB is preserved and a complete image backup is created first. Continue?": "Le fichier doit être un secteur d’amorçage signé de 512 octets. Seule sa zone de code exécutable sera importée ; le BPB FAT actuel est conservé et une sauvegarde complète de l’image est créée auparavant. Continuer ?",
    "Boot code imported": "Code d’amorçage importé", "Boot code imported safely. Backup created:": "Code d’amorçage importé en toute sécurité. Sauvegarde créée :", "Unable to import boot code": "Impossible d’importer le code d’amorçage",
})
CATALOG["ru"].update({
    "Import boot code safely…": "Безопасно импортировать загрузочный код…", "Import boot-sector file": "Импортировать файл загрузочного сектора",
    "Import boot code safely": "Безопасно импортировать загрузочный код",
    "The file must be a signed 512-byte boot sector. Only its executable boot-code area will be imported; the current FAT BPB is preserved and a complete image backup is created first. Continue?": "Файл должен быть подписанным загрузочным сектором размером 512 байт. Импортируется только исполняемая область загрузочного кода; текущий FAT BPB сохраняется, а перед этим создаётся полная резервная копия образа. Продолжить?",
    "Boot code imported": "Загрузочный код импортирован", "Boot code imported safely. Backup created:": "Загрузочный код безопасно импортирован. Создана резервная копия:", "Unable to import boot code": "Не удалось импортировать загрузочный код",
})
CATALOG["ar"].update({
    "Import boot code safely…": "استيراد رمز الإقلاع بأمان…", "Import boot-sector file": "استيراد ملف قطاع الإقلاع",
    "Import boot code safely": "استيراد رمز الإقلاع بأمان",
    "The file must be a signed 512-byte boot sector. Only its executable boot-code area will be imported; the current FAT BPB is preserved and a complete image backup is created first. Continue?": "يجب أن يكون الملف قطاع إقلاع موقّعاً بحجم 512 بايت. لن يُستورد إلا جزء رمز الإقلاع التنفيذي؛ وسيُحفظ FAT BPB الحالي وتُنشأ نسخة احتياطية كاملة للصورة أولاً. هل تريد المتابعة؟",
    "Boot code imported": "تم استيراد رمز الإقلاع", "Boot code imported safely. Backup created:": "تم استيراد رمز الإقلاع بأمان. أُنشئت نسخة احتياطية:", "Unable to import boot code": "تعذر استيراد رمز الإقلاع",
})
CATALOG["ja"].update({
    "Import boot code safely…": "ブートコードを安全にインポート…", "Import boot-sector file": "ブートセクターファイルをインポート",
    "Import boot code safely": "ブートコードを安全にインポート",
    "The file must be a signed 512-byte boot sector. Only its executable boot-code area will be imported; the current FAT BPB is preserved and a complete image backup is created first. Continue?": "ファイルは署名が有効な 512 バイトのブートセクターである必要があります。実行可能なブートコード領域だけをインポートし、現在の FAT BPB を保持したうえで、先にイメージ全体のバックアップを作成します。続行しますか？",
    "Boot code imported": "ブートコードをインポートしました", "Boot code imported safely. Backup created:": "ブートコードを安全にインポートしました。作成したバックアップ：", "Unable to import boot code": "ブートコードをインポートできません",
})
TRANSLATABLE = _catalog_keys()

# v0.8.0 editable fixed-VHD FAT copy workflow.
CATALOG["zh_CN"].update({
    "Create editable fixed VHD copy…": "创建可编辑的固定 VHD 副本…", "Create editable fixed VHD copy": "创建可编辑的固定 VHD 副本",
    "Separate output required": "需要单独的输出文件", "Choose a different output file; the original fixed VHD is kept read-only.": "请选择不同的输出文件；原始固定 VHD 将保持只读。",
    "Creating editable fixed VHD copy": "正在创建可编辑的固定 VHD 副本", "Fixed VHD validation failed": "固定 VHD 验证失败",
})
CATALOG["es"].update({
    "Create editable fixed VHD copy…": "Crear copia VHD fija editable…", "Create editable fixed VHD copy": "Crear copia VHD fija editable",
    "Separate output required": "Se requiere una salida independiente", "Choose a different output file; the original fixed VHD is kept read-only.": "Elija un archivo de salida diferente; el VHD fijo original se mantiene de solo lectura.",
    "Creating editable fixed VHD copy": "Creando copia VHD fija editable", "Fixed VHD validation failed": "Falló la validación del VHD fijo",
})
CATALOG["fr"].update({
    "Create editable fixed VHD copy…": "Créer une copie VHD fixe modifiable…", "Create editable fixed VHD copy": "Créer une copie VHD fixe modifiable",
    "Separate output required": "Une sortie distincte est requise", "Choose a different output file; the original fixed VHD is kept read-only.": "Choisissez un fichier de sortie différent ; le VHD fixe d’origine reste en lecture seule.",
    "Creating editable fixed VHD copy": "Création d’une copie VHD fixe modifiable", "Fixed VHD validation failed": "Échec de la validation du VHD fixe",
})
CATALOG["ru"].update({
    "Create editable fixed VHD copy…": "Создать редактируемую копию фиксированного VHD…", "Create editable fixed VHD copy": "Создать редактируемую копию фиксированного VHD",
    "Separate output required": "Требуется отдельный выходной файл", "Choose a different output file; the original fixed VHD is kept read-only.": "Выберите другой выходной файл; исходный фиксированный VHD останется доступным только для чтения.",
    "Creating editable fixed VHD copy": "Создание редактируемой копии фиксированного VHD", "Fixed VHD validation failed": "Не удалось проверить фиксированный VHD",
})
CATALOG["ar"].update({
    "Create editable fixed VHD copy…": "إنشاء نسخة VHD ثابتة قابلة للتحرير…", "Create editable fixed VHD copy": "إنشاء نسخة VHD ثابتة قابلة للتحرير",
    "Separate output required": "يلزم ملف إخراج منفصل", "Choose a different output file; the original fixed VHD is kept read-only.": "اختر ملف إخراج مختلفاً؛ إذ سيبقى VHD الثابت الأصلي للقراءة فقط.",
    "Creating editable fixed VHD copy": "جارٍ إنشاء نسخة VHD ثابتة قابلة للتحرير", "Fixed VHD validation failed": "فشل التحقق من VHD الثابت",
})
CATALOG["ja"].update({
    "Create editable fixed VHD copy…": "編集可能な固定 VHD コピーを作成…", "Create editable fixed VHD copy": "編集可能な固定 VHD コピーを作成",
    "Separate output required": "別の出力ファイルが必要です", "Choose a different output file; the original fixed VHD is kept read-only.": "別の出力ファイルを選択してください。元の固定 VHD は読み取り専用のまま保持されます。",
    "Creating editable fixed VHD copy": "編集可能な固定 VHD コピーを作成中", "Fixed VHD validation failed": "固定 VHD の検証に失敗しました",
})
TRANSLATABLE = _catalog_keys()

# v0.8.0 controlled DMG conversion workflow.
CATALOG["zh_CN"].update({
    "Convert DMG to raw image…": "将 DMG 转换为原始映像…", "Convert DMG to raw image": "将 DMG 转换为原始映像",
    "DMG adapter unavailable": "DMG 适配器不可用", "Converting DMG to raw image": "正在将 DMG 转换为原始映像",
    "Optional dmg2img executable": "可选 dmg2img 可执行文件", "Locate dmg2img executable": "定位 dmg2img 可执行文件",
    "dmg2img can convert a DMG into a new raw HFS+ image. DiskForge does not mount or write DMG files, and never downloads the adapter automatically.": "dmg2img 可将 DMG 转换为新的原始 HFS+ 映像。DiskForge 不挂载或写入 DMG 文件，也绝不会自动下载该适配器。",
})
CATALOG["es"].update({
    "Convert DMG to raw image…": "Convertir DMG a imagen sin formato…", "Convert DMG to raw image": "Convertir DMG a imagen sin formato",
    "DMG adapter unavailable": "Adaptador DMG no disponible", "Converting DMG to raw image": "Convirtiendo DMG a imagen sin formato",
    "Optional dmg2img executable": "Ejecutable dmg2img opcional", "Locate dmg2img executable": "Localizar ejecutable dmg2img",
    "dmg2img can convert a DMG into a new raw HFS+ image. DiskForge does not mount or write DMG files, and never downloads the adapter automatically.": "dmg2img puede convertir un DMG en una nueva imagen HFS+ sin formato. DiskForge no monta ni escribe archivos DMG y nunca descarga el adaptador automáticamente.",
})
CATALOG["fr"].update({
    "Convert DMG to raw image…": "Convertir le DMG en image brute…", "Convert DMG to raw image": "Convertir le DMG en image brute",
    "DMG adapter unavailable": "Adaptateur DMG indisponible", "Converting DMG to raw image": "Conversion du DMG en image brute",
    "Optional dmg2img executable": "Exécutable dmg2img facultatif", "Locate dmg2img executable": "Localiser l’exécutable dmg2img",
    "dmg2img can convert a DMG into a new raw HFS+ image. DiskForge does not mount or write DMG files, and never downloads the adapter automatically.": "dmg2img peut convertir un DMG en une nouvelle image HFS+ brute. DiskForge ne monte ni n’écrit de fichiers DMG et ne télécharge jamais l’adaptateur automatiquement.",
})
CATALOG["ru"].update({
    "Convert DMG to raw image…": "Преобразовать DMG в необработанный образ…", "Convert DMG to raw image": "Преобразовать DMG в необработанный образ",
    "DMG adapter unavailable": "Адаптер DMG недоступен", "Converting DMG to raw image": "Преобразование DMG в необработанный образ",
    "Optional dmg2img executable": "Необязательный исполняемый файл dmg2img", "Locate dmg2img executable": "Указать исполняемый файл dmg2img",
    "dmg2img can convert a DMG into a new raw HFS+ image. DiskForge does not mount or write DMG files, and never downloads the adapter automatically.": "dmg2img может преобразовать DMG в новый необработанный образ HFS+. DiskForge не монтирует и не записывает файлы DMG и никогда не загружает адаптер автоматически.",
})
CATALOG["ar"].update({
    "Convert DMG to raw image…": "تحويل DMG إلى صورة خام…", "Convert DMG to raw image": "تحويل DMG إلى صورة خام",
    "DMG adapter unavailable": "محول DMG غير متاح", "Converting DMG to raw image": "جارٍ تحويل DMG إلى صورة خام",
    "Optional dmg2img executable": "ملف dmg2img التنفيذي الاختياري", "Locate dmg2img executable": "تحديد موقع ملف dmg2img التنفيذي",
    "dmg2img can convert a DMG into a new raw HFS+ image. DiskForge does not mount or write DMG files, and never downloads the adapter automatically.": "يمكن لـ dmg2img تحويل DMG إلى صورة HFS+ خام جديدة. لا يقوم DiskForge بتركيب ملفات DMG أو الكتابة إليها ولا ينزّل المحول تلقائياً أبداً.",
})
CATALOG["ja"].update({
    "Convert DMG to raw image…": "DMG を RAW イメージに変換…", "Convert DMG to raw image": "DMG を RAW イメージに変換",
    "DMG adapter unavailable": "DMG アダプターを利用できません", "Converting DMG to raw image": "DMG を RAW イメージに変換中",
    "Optional dmg2img executable": "任意の dmg2img 実行可能ファイル", "Locate dmg2img executable": "dmg2img 実行可能ファイルを指定",
    "dmg2img can convert a DMG into a new raw HFS+ image. DiskForge does not mount or write DMG files, and never downloads the adapter automatically.": "dmg2img は DMG を新しい RAW HFS+ イメージに変換できます。DiskForge は DMG ファイルをマウントまたは書き込みせず、アダプターを自動ダウンロードすることもありません。",
})
TRANSLATABLE = _catalog_keys()

# v0.8.0 read-only physical media acquisition queue.
CATALOG["zh_CN"].update({
    "Batch read physical media…": "批量读取物理介质…", "Batch read physical media": "批量读取物理介质",
    "This workflow only reads selected removable or optical media into new image files. It never writes to a physical device. Each completed image receives a SHA-256 audit entry.": "此工作流只会将所选可移动或光学介质读取为新的映像文件。它绝不写入物理设备。每个完成的映像都会获得一条 SHA-256 审计记录。",
    "Choose acquisition output directory": "选择采集输出目录", "Output directory": "输出目录", "Continue after a failed read": "读取失败后继续",
    "Read queue requires selections": "读取队列需要选择内容", "Select one or more removable or optical media and an existing output directory.": "请选择一个或多个可移动或光学介质以及一个现有输出目录。",
    "Reading physical media queue": "正在读取物理介质队列", "Read-only acquisition report": "只读采集报告", "Succeeded:": "成功：", "failed:": "失败：",
})
CATALOG["es"].update({
    "Batch read physical media…": "Leer medios físicos por lotes…", "Batch read physical media": "Leer medios físicos por lotes",
    "This workflow only reads selected removable or optical media into new image files. It never writes to a physical device. Each completed image receives a SHA-256 audit entry.": "Este flujo solo lee los medios extraíbles u ópticos seleccionados en nuevos archivos de imagen. Nunca escribe en un dispositivo físico. Cada imagen completada recibe una entrada de auditoría SHA-256.",
    "Choose acquisition output directory": "Elegir directorio de salida de adquisición", "Output directory": "Directorio de salida", "Continue after a failed read": "Continuar tras una lectura fallida",
    "Read queue requires selections": "La cola de lectura requiere selecciones", "Select one or more removable or optical media and an existing output directory.": "Seleccione uno o más medios extraíbles u ópticos y un directorio de salida existente.",
    "Reading physical media queue": "Leyendo cola de medios físicos", "Read-only acquisition report": "Informe de adquisición de solo lectura", "Succeeded:": "Correctos:", "failed:": "fallidos:",
})
CATALOG["fr"].update({
    "Batch read physical media…": "Lire des médias physiques par lot…", "Batch read physical media": "Lire des médias physiques par lot",
    "This workflow only reads selected removable or optical media into new image files. It never writes to a physical device. Each completed image receives a SHA-256 audit entry.": "Ce flux lit uniquement les médias amovibles ou optiques sélectionnés dans de nouveaux fichiers image. Il n’écrit jamais sur un périphérique physique. Chaque image terminée reçoit une entrée d’audit SHA-256.",
    "Choose acquisition output directory": "Choisir le dossier de sortie d’acquisition", "Output directory": "Dossier de sortie", "Continue after a failed read": "Continuer après une lecture échouée",
    "Read queue requires selections": "La file de lecture requiert des sélections", "Select one or more removable or optical media and an existing output directory.": "Sélectionnez un ou plusieurs médias amovibles ou optiques ainsi qu’un dossier de sortie existant.",
    "Reading physical media queue": "Lecture de la file de médias physiques", "Read-only acquisition report": "Rapport d’acquisition en lecture seule", "Succeeded:": "Réussis :", "failed:": "échoués :",
})
CATALOG["ru"].update({
    "Batch read physical media…": "Пакетно считать физические носители…", "Batch read physical media": "Пакетно считать физические носители",
    "This workflow only reads selected removable or optical media into new image files. It never writes to a physical device. Each completed image receives a SHA-256 audit entry.": "Этот процесс только считывает выбранные съёмные или оптические носители в новые файлы образов. Он никогда не записывает на физическое устройство. Для каждого завершённого образа создаётся запись аудита SHA-256.",
    "Choose acquisition output directory": "Выбрать папку вывода для считывания", "Output directory": "Папка вывода", "Continue after a failed read": "Продолжать после ошибки чтения",
    "Read queue requires selections": "Для очереди чтения требуется выбор", "Select one or more removable or optical media and an existing output directory.": "Выберите один или несколько съёмных либо оптических носителей и существующую папку вывода.",
    "Reading physical media queue": "Чтение очереди физических носителей", "Read-only acquisition report": "Отчёт о считывании только для чтения", "Succeeded:": "Успешно:", "failed:": "ошибок:",
})
CATALOG["ar"].update({
    "Batch read physical media…": "قراءة الوسائط الفعلية دفعةً واحدة…", "Batch read physical media": "قراءة الوسائط الفعلية دفعةً واحدة",
    "This workflow only reads selected removable or optical media into new image files. It never writes to a physical device. Each completed image receives a SHA-256 audit entry.": "يقرأ هذا الإجراء الوسائط القابلة للإزالة أو الضوئية المحددة فقط إلى ملفات صور جديدة. ولا يكتب أبداً على جهاز فعلي. تحصل كل صورة مكتملة على سجل تدقيق SHA-256.",
    "Choose acquisition output directory": "اختر مجلد إخراج الالتقاط", "Output directory": "مجلد الإخراج", "Continue after a failed read": "المتابعة بعد فشل القراءة",
    "Read queue requires selections": "تتطلب قائمة القراءة تحديد عناصر", "Select one or more removable or optical media and an existing output directory.": "حدد وسيطاً واحداً أو أكثر قابلاً للإزالة أو ضوئياً ومجلد إخراج موجوداً.",
    "Reading physical media queue": "جارٍ قراءة قائمة الوسائط الفعلية", "Read-only acquisition report": "تقرير الالتقاط للقراءة فقط", "Succeeded:": "نجح:", "failed:": "فشل:",
})
CATALOG["ja"].update({
    "Batch read physical media…": "物理メディアをバッチ読み取り…", "Batch read physical media": "物理メディアをバッチ読み取り",
    "This workflow only reads selected removable or optical media into new image files. It never writes to a physical device. Each completed image receives a SHA-256 audit entry.": "このワークフローは選択したリムーバブルまたは光学メディアを新しいイメージファイルへ読み取るだけです。物理デバイスへの書き込みは一切行いません。完了した各イメージには SHA-256 監査記録が付与されます。",
    "Choose acquisition output directory": "取得出力ディレクトリを選択", "Output directory": "出力ディレクトリ", "Continue after a failed read": "読み取り失敗後も続行",
    "Read queue requires selections": "読み取りキューには選択が必要です", "Select one or more removable or optical media and an existing output directory.": "1 つ以上のリムーバブルまたは光学メディアと、既存の出力ディレクトリを選択してください。",
    "Reading physical media queue": "物理メディアキューを読み取り中", "Read-only acquisition report": "読み取り専用取得レポート", "Succeeded:": "成功:", "failed:": "失敗:",
})
TRANSLATABLE = _catalog_keys()
