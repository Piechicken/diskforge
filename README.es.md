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
  <a href="README.es.md">Español</a> ·
  <a href="README.fr.md">Français</a> ·
  <a href="README.ru.md">Русский</a> ·
  <a href="README.ar.md">العربية</a>
</p>

> **DiskForge ofrece a las imágenes de disco un verdadero espacio de trabajo de escritorio.** Cree, inspeccione, explore, extraiga, inyecte, convierta, verifique y restaure imágenes de forma segura en una aplicación original y auditable.

## Descargas de la versión

La primera versión pública incluye cuatro paquetes nativos de escritorio. Descargue desde la [página de Releases](https://github.com/Piechicken/diskforge/releases) el paquete correspondiente a **Windows x64**, **Linux x64**, **macOS Intel** o **macOS Apple Silicon**. Cada paquete se compila y valida en GitHub Actions sobre su ejecutor de destino.

| Plataforma | Paquete | Inicio |
|---|---|---|
| Windows x64 | `DiskForge-v0.10.0-windows-x64.zip` | Descomprima y ejecute `DiskForge.exe`. |
| Linux x64 | `DiskForge-v0.10.0-linux-x64.zip` | Descomprima y ejecute `./DiskForge`. |
| macOS Intel | `DiskForge-v0.10.0-macos-intel-x64.zip` | Descomprima y mueva `DiskForge.app` a Aplicaciones. |
| macOS Apple Silicon | `DiskForge-v0.10.0-macos-arm64.zip` | Descomprima y mueva `DiskForge.app` a Aplicaciones. |

## Novedades de v0.8.0

La versión 0.8.0 conserva el espacio documental editable y añade creación de imágenes FAT a partir de una plantilla BPB validada, importación segura de código de arranque de 512 bytes que conserva el BPB de destino y crea una copia de seguridad completa, y copias VHD fijas independientes que pueden reabrirse como sesiones FAT editables tras validar sus datos virtuales y su pie. La VHD original permanece sin modificar; las VHD dinámicas no se abren para escritura nativa.

Los adaptadores externos se declaran de forma transparente: `qemu-img` es opcional para VHDX, VMDK y QCOW2, con informe de capacidad y cancelación; `dmg2img` opcional solo convierte un DMG en una nueva salida HFS+ sin formato. DiskForge no monta ni escribe DMG. La nueva cola de adquisición lee únicamente medios extraíbles u ópticos seleccionados, crea archivos nuevos y registra SHA-256; no contiene una opción de escritura de dispositivos. Todas estas rutas nuevas están traducidas a los seis idiomas de trabajo de las Naciones Unidas y japonés. El flujo de publicación acepta solo etiquetas `v*`, exige coincidencia exacta con los metadatos y falla si la Release ya existe: ningún recurso versionado puede sobrescribirse.

## v0.10.0: reconstrucción ISO segura y disquetes IMG/IMA heredados

La versión de desarrollo actual convierte **IMA** en un formato de imagen sin procesar de primera clase, no solo en un alias de nombre de archivo de IMG. La aplicación de escritorio, la línea de comandos, el diseñador gráfico de recetas y el ejecutor por lotes permiten seleccionar explícitamente salidas `.ima` o `.img`. La creación de imágenes ofrece perfiles FAT12 de disquete heredado verificados al reabrirse: cubren diseños de PC compatibles de 5,25 y 3,5 pulgadas desde 160 KiB hasta 2,88 MiB, incluidos DMF y 82 pistas, además de una geometría CHS personalizada explícita. Una IMA con FAT válida tiene el mismo flujo editable que una IMG con FAT: exploración, vista previa interna, inyección, eliminación, cambio de nombre, atributos, extracción, hash y conversión.

La edición de contenido ISO siempre reconstruye una salida independiente, verifica los archivos preparados y conserva perfiles Rock Ridge/UDF. También puede preservar una única entrada inicial de arranque El Torito verificada. Los catálogos con varias secciones o varios arranques, las áreas de sistema híbridas y los mapeos ambiguos se rechazan expresamente. `iso_edit` de la receta v4 utiliza el mismo núcleo de seguridad.

> Los medios de 128/256 bytes por sector, codificación GCR o sectores variables, disquetes de sectores duros, sistemas de archivos no FAT, pistas protegidas contra copia y capturas flux/bitcell siguen siendo flujos de preservación, inspección, hash y comparación de bytes. DiskForge no los presenta falsamente como imágenes FAT editables de forma segura.

### Contenedores históricos de solo lectura

La línea v0.10 incorpora inspección específica de formato para HFE, DC42, 2MG/2IMG, APRIDISK, CopyQM, SAP, MSA, PSI, PRI, el subconjunto v2.12 restringido de 86F, FDI v2.0, JV3, DMK, UDI v1.0, SCP estándar, HxC MFM canónico, el contenedor de flujo PCE PFI v0 canónico, el contenedor Apple II WOZ 2.0/2.1 canónico, el contenedor de flujo A2R 3.x canónico, el contenedor G64 v0 1541 GCR canónico, el contenedor G71 v0 1571 GCR canónico de doble cara y el contenedor P64 v0 1541 de pulsos NRZI canónico. DC42 y 2MG/2IMG solo exportan áreas de datos verificadas; APRIDISK, CopyQM, SAP, MSA, PSI y JV3 crean un RAW nuevo únicamente cuando su analizador demuestra una disposición normal, rectangular y completa. HFE, PRI, 86F, FDI, DMK, HxC MFM canónico, PCE PFI v0 canónico, WOZ 2.0/2.1 canónico, A2R 3.x canónico, G64 v0 canónico, G71 v0 canónico y P64 v0 canónico solo inspeccionan la estructura del contenedor, del flujo de bits o del flujo magnético: no decodifican pistas, flujo de bits ni flujo y no generan RAW. Todos estos flujos rechazan escritura del origen, conversión genérica, sesiones de sistema de archivos, reparación, dispositivos, sobrescritura y variantes no verificadas. DMK solo valida su cabecera nativa y el directorio IDAM; no interpreta FM/MFM, marcas de datos ni CRC.

## Qué puede hacer

DiskForge reúne los flujos de trabajo más prácticos para gestionar imágenes en una sola interfaz. La ventana principal combina un explorador de imágenes, tabla de directorios, panel de metadatos, registro de actividad y un área de progreso cancelable. Las acciones destructivas se muestran separadas de la exploración habitual.

| Flujo de trabajo | Capacidad nativa | Notas |
|---|---|---|
| Crear imágenes | RAW/IMG/IMA, FAT12, FAT16, FAT32, perfiles FAT12 de disquete heredado verificados, FAT12 con diseño DMF, ISO9660/Joliet/Rock Ridge/UDF y HFS clásico opcional | Cree imágenes FAT editables, perfiles explícitos IMG/IMA o geometría CHS personalizada compatible, DMF documentadas e ISO con medio El Torito opcional. Con `hformat` disponible explícitamente, DiskForge puede crear una nueva imagen HFS clásica independiente en un archivo regular desde 800 KiB; HFS+ permanece de solo lectura. |
| Explorar y extraer | FAT12/16/32, incluidos disquetes DOS antiguos sin etiqueta validada y alias RAW `.vfd`/`.flp`/con sufijo de capacidad de tamaño convencional, candidatos conservadores de archivos eliminados de raíz FAT12/FAT16, inspección de solo lectura de IMD, TD0, CPC DSK, D88, APRIDISK, CopyQM, SAP, MSA, PSI, DC42, 2MG/2IMG, HFE, PRI, 86F restringido, FDI, JV3, DMK, UDI v1.0, SCP estándar, inspección canónica de HxC MFM, inspección del contenedor de flujo PCE PFI v0 canónico, inspección del contenedor Apple II WOZ 2.0/2.1 canónico, inspección del contenedor de flujo A2R 3.x canónico, inspección del contenedor G64 v0 1541 GCR canónico, inspección del contenedor G71 v0 1571 GCR canónico de doble cara e inspección del contenedor P64 v0 1541 de pulsos NRZI canónico, ISO9660/Joliet, contenedores ZIP seguros de varias imágenes con selección explícita, vista de datos VHD fijo y backend NTFS/EXT/HFS clásico/HFS+ opcional de solo lectura | Un ZIP normal solo se materializa en una sesión privada de solo lectura que se limpia automáticamente cuando contiene de una a 64 cargas de imagen seguras de nivel raíz. Una sola carga se abre directamente; un ZIP con varias imágenes exige seleccionar explícitamente una carga en el escritorio, la CLI o el SDK. Nunca pasa a ser escribible ni convertible. Los alias RAW heredados solo se clasifican cuando su sufijo y tamaño exacto en bytes coinciden con una forma convencional de disquete PC de 512 bytes; no se adivinan medios de sectores variables, XDF, GCR, de sectores duros ni de flujo. El árbol y la tabla usan páginas deterministas y caché de ordenación para directorios grandes. Las particiones MBR/GPT validadas siempre se eligen por índice explícito: FAT conserva su ruta de edición existente, mientras que NTFS/EXT/HFS clásico/HFS+ solo se abren en su desplazamiento validado exacto mediante el backend de solo lectura. El doble clic abre un espacio documental no ejecutable para texto, imágenes, archivos comunes, paquetes heredados, ejecutables y datos binarios. El texto permite buscar, guardar una copia y, solo en entradas FAT escribibles, editar y guardar de vuelta. Los VHD fijos se abren mediante una vista RAW temporal de solo lectura sin su pie. |
| Inventariar directorios de imágenes | Escaneo de metadatos locales de solo lectura con informes JSON, CSV o HTML | Analice un directorio local, opcionalmente de forma recursiva, y filtre candidatos conocidos por sufijo, formato reconocido, sistema de archivos, rango de bytes o prefijo SHA-256. SHA-256 y los resúmenes de particiones por registro son opcionales. Cada informe es un archivo nuevo fuera de la raíz analizada; no se modifica ninguna imagen candidata. |
| Cambiar el contenido | Inyección FAT, creación explícita de directorios vacíos, carpetas recursivas, borrado, cambio de nombre, copia entre directorios de archivos y árboles de directorios, movimiento controlado y edición de fechas; edición ISO segura por reconstrucción; inyección NTFS/EXT/HFS clásico controlada opcional | IMG e IMA con FAT comparten el flujo editable. Un directorio vacío solo puede crearse explícitamente en una ruta nueva cuyo padre ya existe; nunca sobrescribe ni crea padres implícitos. Un archivo regular o un árbol completo de directorios puede copiarse a un directorio existente sin sobrescritura; la copia conserva el origen, exige un destino nuevo con el mismo nombre y rechaza un destino de directorio dentro del árbol de origen. Un archivo o árbol de directorios también puede moverse a ese destino: un directorio completa primero una copia cancelable y luego elimina el origen. La cancelación antes de eliminar o un fallo de eliminación conserva ambos árboles completos para su resolución manual; por ello, el movimiento de directorios no se declara atómico. La raíz, los destinos inexistentes o que no son directorios, los conflictos de nombre, las sesiones de solo lectura y los destinos dentro del árbol de origen se rechazan antes de modificar la imagen. El cambio de nombre en el mismo directorio sigue siendo una acción distinta. La eliminación FAT explícita borra un único archivo o árbol de directorios que no sea la raíz tras validar la ruta; es irreversible y no se declara transaccional. La edición ISO crea siempre una imagen nueva, verifica el contenido y conserva Rock Ridge/UDF; solo se mantiene una entrada inicial El Torito verificada y se rechazan diseños de arranque múltiples, híbridos o ambiguos. Con `ntfsprogs`, `e2fsprogs` o `hfsutils` disponibles explícitamente, NTFS/EXT/HFS clásico solo puede recibir archivos regulares nuevos en el directorio raíz de una salida independiente verificada; no se permiten escritura en el origen, desplazamientos de partición, metadatos, renombre, borrado ni sobrescritura. La inyección HFS clásica solo transfiere bifurcaciones de datos sin procesar; HFS+ permanece de solo lectura. |
| Convertir formatos | RAW/IMG/IMA y VHD fijo de forma nativa | IMG e IMA conservan la extensión elegida explícitamente; VHDX, VMDK y QCOW2 utilizan un adaptador `qemu-img` configurado explícitamente. |
| Compactar imágenes FAT | Desfragmentación mediante reconstrucción | Crea una imagen nueva y conserva la original como punto de recuperación. |
| Inspeccionar estructuras y arranque | Visor/editor de 512 bytes, propiedades FAT BPB, modelos originales, MBR neutral y planificación de despliegue, recorte cero y catálogo El Torito | Los modelos conservan BPB y no importan código externo; las operaciones protegidas hacen copia de seguridad y las salidas se crean en archivos nuevos. |
| Verificar y automatizar | SHA-256, estudio gráfico de recetas completas, plan de preflight, revisión de resultados por elemento, recetas JSON e informes de directorio | El esquema v4 añade `iso_edit`, `ntfs_inject`, `ext_inject`, `hfs_inject`, `hfs_create`, `export_listing`, `move`, `fat_mkdir`, `fat_copy`, `fat_rename` y `fat_delete` para FAT, y `fat_metadata` para rutas FAT explícitas; `export_listing` solo crea un informe local de texto/HTML y puede dirigirse a una partición explícita de solo lectura. Los informes de directorio de texto/HTML usan un recorrido completo estable para cada sistema de archivos explorable y partición explícita de solo lectura. El diseñador crea, reabre y edita recetas de conversión, validación, comparación, cambio de tamaño, inyección, creación HFS clásica, extracción y contenedores. `--dry-run` permite revisar acciones sin cambios; las recetas no atendidas rechazan escrituras a dispositivos físicos. |
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
diskforge-cli list partitioned.img --partition 2
diskforge-cli export-listing partitioned.img partition-report.html --html --partition 2
diskforge-cli mkdir-fat demo.img /DOCS  # un directorio vacío nuevo; su padre debe existir
diskforge-cli copy-fat demo.img /README.TXT /DOCS  # conserva el origen; archivo o árbol de directorios completo; sin sobrescritura
diskforge-cli move-fat demo.img /README.TXT /DOCS  # /DOCS debe existir; un árbol usa copia cancelable y después borrado
diskforge-cli delete-fat demo.img /DOCS/OLD.TXT  # un archivo o árbol explícito no raíz; irreversible
diskforge-cli set-fat-metadata demo.img /README.TXT /DOCS/NOTES.TXT --hidden --modified 2024-06-15T12:34:56  # solo rutas FAT explícitas y escribibles
diskforge-cli list archived-image.zip  # una carga de imagen segura de nivel raíz; solo lectura
diskforge-cli list-deleted-fat demo.img  # solo candidatos 8.3 de raíz fija FAT12/FAT16
diskforge-cli recover-deleted-fat demo.img 17 recovered.bin  # nueva salida local; nunca escribe demo.img
diskforge-cli imd-info legacy.imd  # auditoría de pistas/sectores de solo lectura
diskforge-cli convert-imd legacy.imd exported.img  # solo un diseño rectangular de datos normales demostrado
diskforge-cli td0-info legacy.td0  # auditoría de pistas/sectores TD0 ordinaria de solo lectura
diskforge-cli convert-td0 legacy.td0 exported.img  # solo un diseño ordinario rectangular sin indicadores demostrado
diskforge-cli dc42-info disco.dc42  # verifica cabecera, bifurcaciones y sumas de control
diskforge-cli convert-dc42 disco.dc42 exportado.img  # solo bifurcación de datos verificada
diskforge-cli twoimg-info apple.2mg  # valida la estructura 2MG/2IMG
diskforge-cli convert-twoimg apple.2mg exportado.img  # solo bloque de datos DOS/ProDOS
diskforge-cli apridisk-info legacy.dsk  # auditoría APRIDISK basada en firma
diskforge-cli copyqm-info archive.qm  # auditoría CopyQM con suma de control
diskforge-cli sap-info thomson.sap  # auditoría SAP validada por CRC
diskforge-cli msa-info atari.msa  # decodifica y valida todas las pistas MSA
diskforge-cli psi-info media.psi  # flujo de sectores PSI con CRC
diskforge-cli pri-info captura.pri  # estructura de flujo de bits PRI con CRC
diskforge-cli 86f-info captura.86f  # estructura de flujo de bits 86F v2.12 restringida
diskforge-cli fdi-info captura.fdi  # estructura de contenedor multinivel FDI v2.0
diskforge-cli jv3-info disco.jv3  # inspección de contenedor de sectores JV3
diskforge-cli convert-jv3 disco.jv3 exportado.img  # solo diseño normal rectangular demostrado
diskforge-cli dmk-info captura.dmk  # cabecera nativa DMK y estructura de directorio IDAM
diskforge-cli udi-info captura.udi  # solo estructura MFM UDI v1.0 en mayúsculas validada por CRC32
diskforge-cli scp-info captura.scp  # solo estructura SCP estándar de flujo en lectura, sin descodificar el flujo
diskforge-cli mfm-info captura.mfm  # solo estructura canónica de contenedor de flujo de bits HxC MFM
diskforge-cli pfi-info captura.pfi  # solo estructura de contenedor de flujo PCE PFI v0 canónico validada por CRC
diskforge-cli woz-info disco.woz  # solo estructura del contenedor Apple II WOZ 2.0/2.1 canónico
diskforge-cli a2r-info captura.a2r  # solo estructura del contenedor de flujo A2R 3.x canónico
diskforge-cli d64-info disk.d64  # estructura D64 CBM DOS canónica de 35 pistas y cadenas de archivos ordinarios verificadas
diskforge-cli list disk.d64  # lista de directorio CBM DOS de solo lectura
diskforge-cli d71-info disk.d71  # estructura D71 CBM DOS canónica de 70 pistas y doble cara con cadenas de archivos ordinarios verificadas
diskforge-cli list disk.d71  # lista de directorio CBM DOS de doble cara y solo lectura
diskforge-cli d81-info disk.d81  # estructura D81 CBM DOS canónica de 80 pistas y doble cara con cadenas de archivos ordinarios verificadas
diskforge-cli list disk.d81  # lista de directorio D81 CBM DOS de solo lectura
diskforge-cli g64-info disk.g64  # solo estructura del contenedor G64 v0 1541 GCR canónico
diskforge-cli g71-info disco.g71  # solo estructura del contenedor G71 v0 1571 GCR canónico de doble cara
diskforge-cli p64-info captura.p64  # solo estructura CRC-validada del contenedor P64 v0 de pulsos NRZI canónico
diskforge-cli inventory-images ./biblioteca-imagenes informe-biblioteca.json --recursive --include-sha256  # solo lectura; el informe debe estar fuera de la raíz analizada
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
| IMD | Inspección de pistas/sectores de solo lectura | No hay edición directa del sistema de archivos. La exportación estricta crea un RAW nuevo solo tras demostrar un diseño CHS rectangular completo con datos normales. | Sin creación IMD ni conversión en sitio. |
| TD0 | Inspección de pistas/sectores TD0 ordinarios sin compresión avanzada y con comprobaciones CRC documentadas | No hay edición directa del sistema de archivos. La exportación estricta crea un RAW nuevo solo tras demostrar un diseño CHS rectangular completo, sin indicadores, con EOF exacto, coordenadas lógicas/físicas coincidentes y datos ordinarios reconstruidos. | Sin creación TD0, compresión avanzada, conversión en sitio, reparación ni ruta de escritura. |
| PCE PFI v0 | Inspección estructural de contenedor de flujo de solo lectura | Valida sintaxis de fragmentos big-endian, CRC-32 con inicialización cero, contexto de pista, alineación de índices, tokens de pulsos, END de longitud cero y EOF exacto. | No decodifica flujo ni sectores, ni exporta RAW, explora, convierte, edita, repara o escribe. |
| WOZ 2.0/2.1 | Inspección estructural de contenedor Apple II de solo lectura | Valida cabecera WOZ2 firmada, CRC-32 opcional, INFO v2/v3, orden canónico INFO/TMAP/TRKS, rangos opacos de pistas mapeadas, coherencia opcional de mapa FLUX, gramática META UTF-8 acotada y EOF exacto. | No acepta WOZ1 ni decodifica flujo de bits/flujo/sectores, ni exporta RAW, explora, convierte, edita, repara o escribe. |
| A2R 3.x | Inspección estructural de contenedor de flujo de solo lectura | Valida la firma fija A2R3, el primer bloque INFO v1, la gramática acotada de fragmentos little-endian, las entradas de captura RWCP, las entradas de pista resuelta SLVD, la gramática META UTF-8 y EOF exacto. | No acepta A2R1/A2R2 ni decodifica flujo/flujo de bits/sectores, ni exporta RAW, explora, convierte, edita, repara o escribe. |
| D64 (canónico de 35 pistas) | Inspección de sistema de archivos CBM DOS de solo lectura | Acepta únicamente imágenes de 174.848 bytes con sectores de 256 bytes; valida versión/recuentos BAM, cadena de directorio, cadenas ordinarias SEQ/PRG/USR y conteo de bytes del sector final. Los archivos verificados pueden listarse o extraerse directamente o tras materialización ZIP segura. | No admite variantes de 40 pistas/mapa de errores, diseños REL/GEOS, decodificación GCR, reparación, conversión genérica, creación, edición, escritura ni ruta de dispositivo. |
| D71 (canónico de 70 pistas y doble cara) | Inspección de sistema de archivos CBM DOS de solo lectura | Acepta únicamente imágenes de 349.696 bytes con sectores de 256 bytes; valida el indicador de doble cara, las entradas BAM del lado 0, la región de mapa de bits/recuentos BAM del lado 1, la cadena de directorio, las cadenas ordinarias SEQ/PRG/USR, el conteo del sector final y la ausencia de solapamiento de sectores de sistema/directorio/archivos. Los archivos verificados pueden listarse o extraerse directamente o tras materialización ZIP segura. | No admite variantes de 40 pistas/mapa de errores, diseños REL/GEOS, decodificación GCR, reparación, conversión genérica, creación, edición, escritura ni ruta de dispositivo. |
| D81 (canónico de 80 pistas y doble cara) | Inspección de sistema de archivos CBM DOS de solo lectura | Acepta únicamente imágenes de 819.200 bytes con sectores de 256 bytes; valida la cabecera 1581, los dos BAM de 40 entradas, los ID de disco coincidentes, cada mapa de bits/recuento de 40 bits, el directorio lineal canónico de la pista 40, las cadenas ordinarias SEQ/PRG/USR, el conteo del sector final y la ausencia de solapamiento de sectores de sistema/directorio/archivos. Los archivos verificados pueden listarse o extraerse directamente o tras materialización ZIP segura. | No admite variantes de mapa de errores, directorios extendidos, REL/GEOS/particiones CBM, decodificación GCR, reparación, conversión genérica, creación, edición, escritura ni ruta de dispositivo. |
| G64 v0 | Inspección estructural de contenedor 1541 GCR de solo lectura | Valida la firma fija `GCR-1541` versión 0, tablas little-endian acotadas de pistas y velocidad, asignaciones opacas de pistas almacenadas, zonas de velocidad constante o mapeada, ausencia de solapamiento y EOF exacto. | No acepta `GCR-1571` ni decodifica GCR/sectores, ni exporta RAW, explora, convierte, edita, repara o escribe. |
| G71 v0 | Inspección estructural de contenedor 1571 GCR de doble cara y solo lectura | Valida la firma fija `GCR-1571` versión 0, exactamente 168 entradas de media pista, tablas little-endian acotadas de pistas y velocidad, asignaciones opacas de pistas almacenadas, zonas de velocidad constante o mapeada, ausencia de solapamiento y EOF exacto. | Los bytes GCR permanecen opacos: no decodifica GCR/sectores ni exporta RAW, explora, abre una sesión de sistema de archivos, convierte, edita, repara o escribe. |
| P64 v0 | Inspección estructural de contenedor 1541 de pulsos NRZI de solo lectura | Valida la firma fija `P64-1541` versión 0, indicadores definidos, CRC-32 de flujo completo y de cada fragmento, trama HTPx acotada, coordenadas únicas de media pista/lado, recuentos de bytes de flujo por rangos, DONE final vacío y EOF exacto. | Los datos NRZI codificados por rangos permanecen opacos: no decodifica pulsos/GCR/sectores, ni exporta RAW, explora, convierte, edita, repara o escribe. |
| FAT12 / FAT16 / FAT32 | Sí | FAT sigue siendo editable. FAT12/FAT16 añade candidatos conservadores 8.3 eliminados en raíz fija; la recuperación solo copia un clúster único actualmente libre a un archivo local nuevo. | Sí |
| ISO9660 / Joliet | Sí | Lectura y extracción | Crear desde carpeta |
| VHD fijo | Sí | Vista de datos temporal de solo lectura y conversión | Sí |
| VHDX / VMDK / QCOW2 | Con adaptador | Mediante flujo de conversión | Con adaptador |
| NTFS / EXT2 / EXT3 / EXT4 | Indicio de firma o partición | Lectura/listado/extracción con Sleuth Kit opcional en offset-0 o una partición MBR/GPT validada elegida explícitamente; hay informes de directorio de texto/HTML. La inyección controlada a nueva salida con `ntfsprogs` / `e2fsprogs` sigue limitada a offset-0 independiente | La exploración es de solo lectura. La inyección usa solo backend externo: volúmenes independientes offset-0, archivos regulares nuevos en raíz, sin sobrescritura; se requieren SHA-256 del origen, SHA-256 de lectura y validación del sistema. |
| HFS / HFS+ | Indicio de firma o partición | Lectura/listado/extracción de fork de datos con Sleuth Kit opcional en offset-0 o una partición MBR/GPT validada elegida explícitamente; hay informes de directorio de texto/HTML. HFS clásico admite además inyección controlada a nueva salida y creación verificada de un archivo regular mediante `hfsutils` configurado | La exploración de particiones es de solo lectura. Creación solo de HFS clásico: archivo regular nuevo, al menos 800 KiB en unidades de 512 bytes, etiqueta ASCII segura de 1–27 caracteres, sin dispositivo, mapa de particiones, salida existente ni `-f`; la firma HFS y SHA-256 se verifican antes de la promoción atómica. La inyección sigue limitada a volúmenes independientes offset-0, archivos regulares nuevos y seguros en raíz, solo bifurcaciones de datos sin procesar y sin sobrescritura; se requiere SHA-256 del origen y de cada carga leída. HFS+ permanece de solo lectura; sin escritura HFS+ con diario, reconstrucción de forks de recursos ni reparación. |
| Contenedor de imágenes ZIP (`.zip`) | Estructura ZIP y de una a 64 cargas candidatas validadas | Solo lectura/listado/extracción/informe tras materialización temporal autolimpiable; un archivo con varias imágenes exige un nombre seleccionado explícitamente | Sin creación, conversión, edición del sistema de archivos ni escritura del archivo. Cada carga raíz no cifrada Stored/Deflated `.img`, `.ima`, `.bin`, `.dd`, `.dmf`, `.vfd`, `.flp`, alias de capacidad, `.d64`, `.d71`, `.d81`, `.iso` o `.hfs`, de hasta 2 GiB, debe validarse; cualquier miembro inseguro rechaza el contenedor. |
| DMG | Indicio de firma | Sin modificación nativa | Use un flujo externo compatible. |

DiskForge expone con claridad las rutas de edición no compatibles en lugar de intentar escrituras inseguras. El PCE PFI v0 canónico solo valida límites de fragmentos big-endian publicados, CRC, contextos de pista, índices y sintaxis de tokens de pulso; los bytes de flujo permanecen opacos. No decodifica flujo, MFM/FM ni sectores, ni exporta RAW, explora, convierte, repara o escribe. El G71 v0 canónico solo valida la firma fija `GCR-1571` versión 0, exactamente 168 entradas de media pista, tablas little-endian acotadas de pistas y velocidad, asignaciones opacas de pistas almacenadas, zonas de velocidad constante o mapeada, ausencia de solapamiento y EOF exacto; los bytes GCR permanecen opacos y no decodifica GCR ni sectores, ni exporta RAW, explora, abre una sesión de sistema de archivos, convierte, repara o escribe. El P64 v0 canónico solo valida la cabecera fija `P64-1541` versión 0, indicadores definidos, CRC-32 del flujo completo y de cada fragmento, trama HTPx acotada, coordenadas únicas de media pista/lado, recuentos de bytes de flujo por rangos, DONE final vacío y EOF exacto; los datos NRZI codificados por rangos permanecen opacos y no decodifica pulsos, GCR ni sectores, ni exporta RAW, explora, convierte, repara o escribe. El WOZ 2.0/2.1 canónico solo valida cabecera WOZ2 firmada, CRC opcional, INFO v2/v3, diseño INFO/TMAP/TRKS canónico, rangos opacos de pistas mapeadas, coherencia opcional de mapa FLUX, gramática META acotada y EOF exacto; no acepta WOZ1 ni decodifica flujo de bits, flujo o sectores, ni exporta RAW, explora, convierte, repara o escribe. El A2R 3.x canónico solo valida la firma fija A2R3, el primer INFO v1, fragmentos little-endian acotados, capturas RWCP, pistas resueltas SLVD, META UTF-8 y EOF exacto; no acepta A2R1/A2R2 ni decodifica flujo, flujo de bits o sectores, ni exporta RAW, explora, convierte, repara o escribe. El G64 v0 canónico solo valida la firma fija `GCR-1541` versión 0, tablas little-endian acotadas de pistas y velocidad, asignaciones opacas de pistas almacenadas, zonas de velocidad constante o mapeada, ausencia de solapamiento y EOF exacto; no acepta `GCR-1571`, no decodifica GCR ni sectores y no exporta RAW, explora, convierte, repara ni escribe. El inventario por lotes es un flujo local de informes de solo lectura, no un escáner forense ni una mutación desatendida: acepta un directorio existente que no sea enlace simbólico, ignora enlaces, reconoce solo sufijos de imagen conocidos, encuentra como máximo 10.000 archivos regulares, excluye archivos mayores de 16 GiB y escribe únicamente un informe JSON/CSV/HTML nuevo fuera de la raíz analizada. No monta imágenes, no inspecciona dispositivos físicos, no sobrescribe informes ni entra en el esquema por lotes v4. IMD se inspecciona como un contenedor de sectores de disquete y no se trata automáticamente como sistema de archivos RAW o escribible. Solo se puede exportar un RAW nuevo desde un diseño CHS rectangular completo con número/tamaño de sector fijos, identificadores consecutivos `1..N`, sin mapas opcionales y datos de sector normales, incluido el relleno normal comprimido. Se rechazan geometría irregular, sectores ausentes/eliminados/defectuosos, diseños variables, registros duplicados, mapas, bytes finales, destinos de dispositivo, sobrescrituras, escritura IMD y toda afirmación de flujo de bits o flujo magnético. TD0 también es un contenedor de sectores, no un sistema de archivos RAW o escribible: solo se inspeccionan registros `TD` ordinarios sin compresión avanzada y se validan los CRC de cabecera/comentario/pista/sector. La exportación RAW nueva requiere EOF exacto, sectores sin indicadores, CHS físico y lógico coincidente, geometría fija y reconstrucción exacta de datos ordinarios raw/patrón repetido/RLE. Se rechazan `td` con compresión avanzada, multivolumen, fallos CRC, indicadores o datos ausentes, densidad mixta, geometría irregular, sobrescritura de salida, escritura/edición/reparación TD0, dispositivos y afirmaciones de flujo de bits o flujo magnético. La recuperación de archivos FAT eliminados es un flujo limitado de **copia de candidatos**, no una recuperación forense genérica: solo acepta ranuras 8.3 ordinarias de raíz fija FAT12/FAT16, con carga positiva de un solo clúster y clúster inicial actualmente libre. El primer carácter del nombre eliminado no está disponible y los bytes candidatos pueden estar obsoletos o sobrescritos; no se afirma el nombre ni la integridad originales. Se rechazan FAT32, subdirectorios, nombres largos, cadenas de cero o varios clústeres, clústeres ocupados, escrituras en el origen, sobrescritura de salida existente, recuperación de dispositivos y recuperación por lotes. Un ZIP normal es un contenedor limitado de **imágenes de solo lectura**, no un sistema de archivos general ni una fuente de conversión: puede contener de una a 64 cargas raíz seguras, no cifradas y Stored/Deflated, con extensiones directas aprobadas y de hasta 2 GiB cada una. Una sola carga se abre directamente; varias cargas exigen un nombre raíz exacto seleccionado explícitamente en el escritorio, la CLI o el SDK. Se rechazan carpetas, nombres inseguros, cifrado, compresión desconocida, cargas vacías/excesivas/desconocidas, más de 64 entradas, contenedores recursivos, cadenas de discos virtuales, conversión y toda escritura ZIP; los bytes temporales se eliminan al cerrar, ante error y al cancelar. El movimiento FAT acepta un archivo regular o un árbol completo de directorios y un directorio de destino existente; nunca sobrescribe ni fusiona entradas. Los árboles usan copiar y después eliminar de forma cancelable; cancelar antes de eliminar o un fallo de eliminación conserva ambos árboles completos y no se declara atómico. Los lotes de metadatos FAT se limitan a entradas existentes enumeradas explícitamente en una imagen FAT escribible o una partición FAT elegida de forma explícita. Solo pueden establecer o borrar los bits estándar de solo lectura, oculto, sistema y archivo, y aplicar horas FAT de creación, modificación o acceso sin zona horaria proporcionadas por quien llama. Se rechazan solicitudes vacías, rutas raíz o duplicadas, comodines, recursión, horas actuales implícitas, sistemas que no son FAT, dispositivos, ACL/ADS/propiedad y selección automática. La vista previa identifica la escritura, pero no se declara reversión todo-o-nada entre varias actualizaciones de directorio FAT.  Configure `qemu-img` en **Tools → Preferences** cuando necesite convertir discos virtuales; la exploración NTFS/EXT/HFS/HFS+ de solo lectura requiere `fls` e `icat` de Sleuth Kit locales, y la inyección controlada opcional requiere `ntfscp`/`ntfsls`/`ntfscat`, `debugfs`/`e2fsck` o, solo para HFS clásico, `hmount`/`hcopy`/`hls` para inyección o `hformat` para creación verificada, configurados explícitamente. La aplicación nunca descarga, monta ni ejecuta una herramienta externa silenciosamente. Consulte [FILESYSTEM_INJECTION.md](docs/FILESYSTEM_INJECTION.md).

## Calidad de ingeniería

El proyecto cubre con pruebas automatizadas creación FAT, movimiento seguro de archivos y árboles de directorios, materialización y limpieza seguras de una carga de imagen ZIP seleccionada explícitamente, recuperación conservadora de candidatos FAT eliminados, inspección IMD de solo lectura y exportación RAW estricta, inspección TD0 de solo lectura y exportación RAW estricta con CRC, actualizaciones explícitas de metadatos FAT en CLI/SDK/lotes/escritorio, filtrado de inventario de imágenes por lotes de solo lectura e informes JSON/CSV/HTML, y edición FAT, ISO arrancable y El Torito, preservación BPB y copias de los modelos originales, exploración temporal VHD, planificación de despliegue, informes de cola cero, arrastrar y soltar, edición completa de recetas y preflight por lotes, vista documental/búsqueda/guardado de vuelta, recorrido de directorios paginado, el espacio de trabajo completo en siete idiomas, API pública, configuración portátil, centro de tareas, fuentes, reconocimiento óptico multiplataforma, controles de escritura y compactación FAT. pytest usa configuración estricta y trata los avisos como errores; la interfaz también se valida fuera de pantalla. La integración continua ejecuta pruebas en Windows, Linux, macOS Intel y macOS Apple Silicon, y empaqueta cada destino nativo. Las etiquetas se verifican contra los metadatos y una Release preexistente detiene el flujo en vez de sobrescribir recursos.

```bash
QT_QPA_PLATFORM=offscreen pytest
QT_QPA_PLATFORM=offscreen python scripts/gui_smoke.py
```

Consulte [BUILDING.md](docs/BUILDING.md) para detalles de compilación y publicación. La nota de validación visual está disponible en [gui_validation.md](artifacts/gui_validation.md).

## Contribuir

Se aceptan issues y pull requests. Mantenga los cambios enfocados, añada pruebas de regresión para los cambios de comportamiento y nunca incluya imágenes de disco reales, credenciales, rutas privadas ni resultados de compilación generados en los commits.

## Licencia

DiskForge se distribuye bajo la [licencia MIT](LICENSE).
