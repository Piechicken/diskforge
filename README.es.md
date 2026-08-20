<p align="center">
  <img src="assets/diskforge-workspace.png" alt="Espacio de trabajo de DiskForge con una imagen FAT abierta" width="900">
</p>

<h1 align="center">DiskForge</h1>

<p align="center"><strong>Estudio multiplataforma de imágenes de disco para crear, explorar, convertir y restaurar con seguridad.</strong></p>

<p align="center">
  <a href="https://github.com/Piechicken/diskforge/actions/workflows/ci.yml"><img src="https://github.com/Piechicken/diskforge/actions/workflows/ci.yml/badge.svg?branch=main" alt="Estado de compilación"></a>
  <a href="https://github.com/Piechicken/diskforge/releases"><img src="https://img.shields.io/github/v/release/Piechicken/diskforge?display_name=tag&color=7C3AED" alt="Última versión"></a>
  <a href="LICENSE"><img src="https://img.shields.io/badge/license-MIT-0EA5E9.svg" alt="Licencia MIT"></a>
  <img src="https://img.shields.io/badge/Python-3.10%2B-2563EB.svg" alt="Python 3.10 o posterior">
  <img src="https://img.shields.io/badge/GUI-Qt-16A34A.svg" alt="Interfaz Qt">
</p>

<p align="center">
  <a href="README.md">English</a> ·
  <a href="README.zh-CN.md">简体中文</a> ·
  <a href="README.ja.md">日本語</a> ·
  <a href="README.es.md">Español</a>
</p>

> **DiskForge ofrece a las imágenes de disco un verdadero espacio de trabajo de escritorio.** Cree, inspeccione, explore, extraiga, inyecte, convierta, verifique y restaure imágenes de forma segura en una aplicación original y auditable.

## Descargas de la versión

La primera versión pública incluye cuatro paquetes nativos de escritorio. Descargue desde la [página de Releases](https://github.com/Piechicken/diskforge/releases) el paquete correspondiente a **Windows x64**, **Linux x64**, **macOS Intel** o **macOS Apple Silicon**. Cada paquete se compila y valida en GitHub Actions sobre su ejecutor de destino.

| Plataforma | Paquete | Inicio |
|---|---|---|
| Windows x64 | `DiskForge-v0.8.0-windows-x64.zip` | Descomprima y ejecute `DiskForge.exe`. |
| Linux x64 | `DiskForge-v0.8.0-linux-x64.zip` | Descomprima y ejecute `./DiskForge`. |
| macOS Intel | `DiskForge-v0.8.0-macos-intel-x64.zip` | Descomprima y mueva `DiskForge.app` a Aplicaciones. |
| macOS Apple Silicon | `DiskForge-v0.8.0-macos-arm64.zip` | Descomprima y mueva `DiskForge.app` a Aplicaciones. |

## Novedades de v0.8.0

La versión 0.8.0 conserva el espacio documental editable y añade creación de imágenes FAT a partir de una plantilla BPB validada, importación segura de código de arranque de 512 bytes que conserva el BPB de destino y crea una copia de seguridad completa, y copias VHD fijas independientes que pueden reabrirse como sesiones FAT editables tras validar sus datos virtuales y su pie. La VHD original permanece sin modificar; las VHD dinámicas no se abren para escritura nativa.

Los adaptadores externos se declaran de forma transparente: `qemu-img` es opcional para VHDX, VMDK y QCOW2, con informe de capacidad y cancelación; `dmg2img` opcional solo convierte un DMG en una nueva salida HFS+ sin formato. DiskForge no monta ni escribe DMG. La nueva cola de adquisición lee únicamente medios extraíbles u ópticos seleccionados, crea archivos nuevos y registra SHA-256; no contiene una opción de escritura de dispositivos. Todas estas rutas nuevas están traducidas a los seis idiomas de trabajo de las Naciones Unidas y japonés. El flujo de publicación acepta solo etiquetas `v*`, exige coincidencia exacta con los metadatos y falla si la Release ya existe: ningún recurso versionado puede sobrescribirse.

## v0.10.0.dev0: reconstrucción ISO segura y disquetes IMG/IMA heredados

La versión de desarrollo actual convierte **IMA** en un formato de imagen sin procesar de primera clase, no solo en un alias de nombre de archivo de IMG. La aplicación de escritorio, la línea de comandos, el diseñador gráfico de recetas y el ejecutor por lotes permiten seleccionar explícitamente salidas `.ima` o `.img`. La creación de imágenes ofrece perfiles FAT12 de disquete heredado verificados al reabrirse: cubren diseños de PC compatibles de 5,25 y 3,5 pulgadas desde 160 KiB hasta 2,88 MiB, incluidos DMF y 82 pistas, además de una geometría CHS personalizada explícita. Una IMA con FAT válida tiene el mismo flujo editable que una IMG con FAT: exploración, vista previa interna, inyección, eliminación, cambio de nombre, atributos, extracción, hash y conversión.

La edición de contenido ISO siempre reconstruye una salida independiente, verifica los archivos preparados y conserva perfiles Rock Ridge/UDF. También puede preservar una única entrada inicial de arranque El Torito verificada. Los catálogos con varias secciones o varios arranques, las áreas de sistema híbridas y los mapeos ambiguos se rechazan expresamente. `iso_edit` de la receta v4 utiliza el mismo núcleo de seguridad.

> Los medios de 128/256 bytes por sector, codificación GCR o sectores variables, disquetes de sectores duros, sistemas de archivos no FAT, pistas protegidas contra copia y capturas flux/bitcell siguen siendo flujos de preservación, inspección, hash y comparación de bytes. DiskForge no los presenta falsamente como imágenes FAT editables de forma segura.

## Qué puede hacer

DiskForge reúne los flujos de trabajo más prácticos para gestionar imágenes en una sola interfaz. La ventana principal combina un explorador de imágenes, tabla de directorios, panel de metadatos, registro de actividad y un área de progreso cancelable. Las acciones destructivas se muestran separadas de la exploración habitual.

| Flujo de trabajo | Capacidad nativa | Notas |
|---|---|---|
| Crear imágenes | RAW/IMG/IMA, FAT12, FAT16, FAT32, perfiles FAT12 de disquete heredado verificados, FAT12 con diseño DMF, ISO9660/Joliet/Rock Ridge/UDF y HFS clásico opcional | Cree imágenes FAT editables, perfiles explícitos IMG/IMA o geometría CHS personalizada compatible, DMF documentadas e ISO con medio El Torito opcional. Con `hformat` disponible explícitamente, DiskForge puede crear una nueva imagen HFS clásica independiente en un archivo regular desde 800 KiB; HFS+ permanece de solo lectura. |
| Explorar y extraer | FAT12/16/32, incluidos disquetes DOS antiguos sin etiqueta validada, ISO9660/Joliet, vista de datos VHD fijo y backend NTFS/EXT/HFS clásico/HFS+ opcional de solo lectura | El árbol y la tabla usan páginas deterministas y caché de ordenación para directorios grandes. El doble clic abre un espacio documental no ejecutable para texto, imágenes, archivos comunes, paquetes heredados, ejecutables y datos binarios. El texto permite buscar, guardar una copia y, solo en entradas FAT escribibles, editar y guardar de vuelta. Los VHD fijos se abren mediante una vista RAW temporal de solo lectura sin su pie. |
| Cambiar el contenido | Inyección FAT, carpetas recursivas, borrado y edición de fechas; edición ISO segura por reconstrucción; inyección NTFS/EXT/HFS clásico controlada opcional | IMG e IMA con FAT comparten el flujo editable. La edición ISO crea siempre una imagen nueva, verifica el contenido y conserva Rock Ridge/UDF; solo se mantiene una entrada inicial El Torito verificada y se rechazan diseños de arranque múltiples, híbridos o ambiguos. Con `ntfsprogs`, `e2fsprogs` o `hfsutils` disponibles explícitamente, NTFS/EXT/HFS clásico solo puede recibir archivos regulares nuevos en el directorio raíz de una salida independiente verificada; no se permiten escritura en el origen, desplazamientos de partición, metadatos, renombre, borrado ni sobrescritura. La inyección HFS clásica solo transfiere bifurcaciones de datos sin procesar; HFS+ permanece de solo lectura. |
| Convertir formatos | RAW/IMG/IMA y VHD fijo de forma nativa | IMG e IMA conservan la extensión elegida explícitamente; VHDX, VMDK y QCOW2 utilizan un adaptador `qemu-img` configurado explícitamente. |
| Compactar imágenes FAT | Desfragmentación mediante reconstrucción | Crea una imagen nueva y conserva la original como punto de recuperación. |
| Inspeccionar estructuras y arranque | Visor/editor de 512 bytes, propiedades FAT BPB, modelos originales, MBR neutral y planificación de despliegue, recorte cero y catálogo El Torito | Los modelos conservan BPB y no importan código externo; las operaciones protegidas hacen copia de seguridad y las salidas se crean en archivos nuevos. |
| Verificar y automatizar | SHA-256, estudio gráfico de recetas completas, plan de preflight, revisión de resultados por elemento y recetas JSON | El esquema v4 añade `iso_edit`, `ntfs_inject`, `ext_inject`, `hfs_inject` y `hfs_create`; el diseñador crea, reabre y edita recetas de conversión, validación, comparación, cambio de tamaño, inyección, creación HFS clásica, extracción y contenedores. `--dry-run` permite revisar acciones sin cambios; las recetas no atendidas rechazan escrituras a dispositivos físicos. |
| Crear paquetes redistribuibles | Contenedores `.dfb` autenticados y archivos autoextraíbles `.pyz` multiimagen verificados con SHA-256 | Los contenedores admiten cifrado AES-256-GCM opcional, compresión, comentarios y verificación por archivo. Cada paquete nativo también incluye `DiskForgeExtractor` independiente para verificar y extraer cargas `.pyz` sin que el destinatario instale Python previamente. |
| Leer y escribir medios físicos | Lectura y restauración en flujo | Rechaza discos del sistema, destinos montados y tamaños incompatibles; requiere confirmación escrita. Los medios ópticos detectados son de solo lectura y se exportan a ISO por defecto. |
| Formateo de disquete de bajo nivel | Disquete de controlador Linux y backends de disquete USB UFI detectados | `fdformat` se limita a nodos de controlador estándar. Un candidato USB UFI debe estar asociado por sysfs a un medio extraíble, identificarse mediante `ufiformat -i`, usar una capacidad indicada explícitamente y la frase `FORMAT_FLOPPY`; siempre se verifica con `-V`. La creación de FAT sigue siendo una operación independiente con nueva confirmación; cada modelo requiere aceptación con hardware real. |

## Seguridad primero

> Una utilidad de imágenes de disco debe hacer que las operaciones peligrosas sean **difíciles de activar por accidente**.

DiskForge no monta imágenes ni escribe dispositivos físicos automáticamente. El despliegue FAT primero crea una imagen MBR neutral revisable y nunca evita la protección de escritura física. Antes de una escritura física comprueba la capacidad, el estado de montaje y si se trata de un disco del sistema; después exige la frase exacta `ERASE`. La ruta de escritura puede verificar los bytes al finalizar. Los cambios del sector de arranque también crean primero una copia de seguridad de la imagen completa. Practique siempre con imágenes desechables antes de operar con medios irreemplazables.

## Configuración portátil

Inicie `diskforge --portable` para guardar idioma, tema, fuente, recientes, vistas y ruta de herramientas en `DiskForgeData/diskforge.ini` dentro del directorio actual. Use `--portable=DIR`, `--portable-directory DIR` o `DISKFORGE_PORTABLE_DIR` para elegir la ubicación. El modo usa un INI portátil y no requiere registro del sistema.

## Empiece en minutos

### Ejecutar desde el código fuente

```bash
python -m pip install -e '.[dev]'
diskforge
```

### Usar la línea de comandos

```bash
diskforge-cli create-fat demo.img --size-mib 32 --fat 16
diskforge-cli info demo.img
diskforge-cli list demo.img
diskforge-cli create-iso carpeta arrancable.iso --boot-image boot.img --boot-media noemul
diskforge-cli inject-ntfs standalone.ntfs revised.ntfs PAYLOAD.TXT
diskforge-cli inject-ext standalone.ext4 revised.ext4 PAYLOAD.TXT
diskforge-cli inject-hfs standalone.hfs revised.hfs PAYLOAD.TXT
diskforge-cli create-hfs created.hfs --size-kib 800 --label DISKFORGE
diskforge-cli ntfs-inject-status
diskforge-cli ext-inject-status
diskforge-cli hfs-inject-status
diskforge-cli hfs-create-status
diskforge-cli boot-templates
diskforge-cli prepare-fat-deployment demo.img demo-deploy.img
diskforge-cli batch recipe.json --dry-run
diskforge-cli --help
```

### Crear un paquete nativo

```bash
python scripts/build.py
```

Compile en cada sistema operativo de destino para generar su aplicación nativa. El flujo de trabajo del repositorio realiza estas compilaciones automáticamente para los cuatro objetivos de publicación.

## Cobertura de formatos

| Formato o sistema de archivos | Inspección | Explorar / modificar | Crear / convertir |
|---|---:|---:|---:|
| RAW / IMG / IMA / BIN | Sí | Cargas FAT | Sí |
| FAT12 / FAT16 / FAT32 | Sí | Sí | Sí |
| ISO9660 / Joliet | Sí | Lectura y extracción | Crear desde carpeta |
| VHD fijo | Sí | Vista de datos temporal de solo lectura y conversión | Sí |
| VHDX / VMDK / QCOW2 | Con adaptador | Mediante flujo de conversión | Con adaptador |
| NTFS / EXT2 / EXT3 / EXT4 | Indicio de firma o partición | Lectura/listado/extracción con Sleuth Kit opcional; inyección controlada a una nueva salida con `ntfsprogs` / `e2fsprogs` configurados | Solo backend externo: volúmenes independientes offset-0, archivos regulares nuevos en raíz, sin sobrescritura; se requieren SHA-256 del origen, SHA-256 de lectura y validación del sistema. |
| HFS / HFS+ | Indicio de firma o partición | Lectura/listado/extracción de fork de datos con Sleuth Kit opcional; HFS clásico admite además inyección controlada a nueva salida y creación verificada de un archivo regular mediante `hfsutils` configurado | Creación solo de HFS clásico: archivo regular nuevo, al menos 800 KiB en unidades de 512 bytes, etiqueta ASCII segura de 1–27 caracteres, sin dispositivo, mapa de particiones, salida existente ni `-f`; la firma HFS y SHA-256 se verifican antes de la promoción atómica. La inyección sigue limitada a volúmenes independientes offset-0, archivos regulares nuevos y seguros en raíz, solo bifurcaciones de datos sin procesar y sin sobrescritura; se requiere SHA-256 del origen y de cada carga leída. HFS+ permanece de solo lectura; sin escritura HFS+ con diario, reconstrucción de forks de recursos ni reparación. |
| DMG | Indicio de firma | Sin modificación nativa | Use un flujo externo compatible. |

DiskForge expone con claridad las rutas de edición no compatibles en lugar de intentar escrituras inseguras. Configure `qemu-img` en **Tools → Preferences** cuando necesite convertir discos virtuales; la exploración NTFS/EXT/HFS/HFS+ de solo lectura requiere `fls` e `icat` de Sleuth Kit locales, y la inyección controlada opcional requiere `ntfscp`/`ntfsls`/`ntfscat`, `debugfs`/`e2fsck` o, solo para HFS clásico, `hmount`/`hcopy`/`hls` para inyección o `hformat` para creación verificada, configurados explícitamente. La aplicación nunca descarga, monta ni ejecuta una herramienta externa silenciosamente. Consulte [FILESYSTEM_INJECTION.md](docs/FILESYSTEM_INJECTION.md).

## Calidad de ingeniería

El proyecto cubre con pruebas automatizadas creación y edición FAT, ISO arrancable y El Torito, preservación BPB y copias de los modelos originales, exploración temporal VHD, planificación de despliegue, informes de cola cero, arrastrar y soltar, edición completa de recetas y preflight por lotes, vista documental/búsqueda/guardado de vuelta, recorrido de directorios paginado, el espacio de trabajo completo en siete idiomas, API pública, configuración portátil, centro de tareas, fuentes, reconocimiento óptico multiplataforma, controles de escritura y compactación FAT. pytest usa configuración estricta y trata los avisos como errores; la interfaz también se valida fuera de pantalla. La integración continua ejecuta pruebas en Windows, Linux, macOS Intel y macOS Apple Silicon, y empaqueta cada destino nativo. Las etiquetas se verifican contra los metadatos y una Release preexistente detiene el flujo en vez de sobrescribir recursos.

```bash
QT_QPA_PLATFORM=offscreen pytest
QT_QPA_PLATFORM=offscreen python scripts/gui_smoke.py
```

Consulte [BUILDING.md](docs/BUILDING.md) para detalles de compilación y publicación. La nota de validación visual está disponible en [gui_validation.md](artifacts/gui_validation.md).

## Contribuir

Se aceptan issues y pull requests. Mantenga los cambios enfocados, añada pruebas de regresión para los cambios de comportamiento y nunca incluya imágenes de disco reales, credenciales, rutas privadas ni resultados de compilación generados en los commits.

## Licencia

DiskForge se distribuye bajo la [licencia MIT](LICENSE).
