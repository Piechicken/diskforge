<p align="center">
  <img src="assets/diskforge-workspace.png" alt="FAT イメージを開いた DiskForge のワークスペース" width="900">
</p>

<h1 align="center">DiskForge</h1>

<p align="center"><strong>イメージの作成、探索、変換、安全な復元を行うクロスプラットフォームのディスクイメージ・スタジオ。</strong></p>

<p align="center">
  <a href="https://github.com/Piechicken/diskforge/actions/workflows/ci.yml"><img src="https://github.com/Piechicken/diskforge/actions/workflows/ci.yml/badge.svg?branch=main" alt="Build status"></a>
  <a href="https://github.com/Piechicken/diskforge/releases"><img src="https://img.shields.io/github/v/release/Piechicken/diskforge?display_name=tag&color=7C3AED" alt="Latest release"></a>
  <a href="LICENSE"><img src="https://img.shields.io/badge/license-MIT-0EA5E9.svg" alt="MIT License"></a>
  <img src="https://img.shields.io/badge/Python-3.10%2B-2563EB.svg" alt="Python 3.10 or newer">
  <img src="https://img.shields.io/badge/GUI-Qt-16A34A.svg" alt="Qt GUI">
</p>

<p align="center">
  <a href="README.md">English</a> ·
  <a href="README.zh-CN.md">简体中文</a> ·
  <a href="README.ja.md">日本語</a> ·
  <a href="README.es.md">Español</a>
</p>

> **DiskForge はディスクイメージに本格的なデスクトップ作業領域を提供します。** 作成、検査、閲覧、抽出、注入、変換、検証、安全な復元を、独自実装で監査可能な一つのアプリケーションにまとめています。

## リリースのダウンロード

初回の公開リリースでは、四つのネイティブ・デスクトップパッケージを提供します。[Releases ページ](https://github.com/Piechicken/diskforge/releases)から、**Windows x64**、**Linux x64**、**macOS Intel**、または **macOS Apple Silicon** 用のパッケージを選んでください。各パッケージは対象プラットフォーム上の GitHub Actions で構築・検証されます。

| プラットフォーム | パッケージ | 起動方法 |
|---|---|---|
| Windows x64 | `DiskForge-v0.8.0-windows-x64.zip` | 展開して `DiskForge.exe` を実行します。 |
| Linux x64 | `DiskForge-v0.8.0-linux-x64.zip` | 展開して `./DiskForge` を実行します。 |
| macOS Intel | `DiskForge-v0.8.0-macos-intel-x64.zip` | 展開し、`DiskForge.app` を Applications に移動します。 |
| macOS Apple Silicon | `DiskForge-v0.8.0-macos-arm64.zip` | 展開し、`DiskForge.app` を Applications に移動します。 |

## v0.8.0 の文書型ワークスペースと不変リリース

v0.8.0 は編集可能な文書型ワークスペースを維持しつつ、検証済み BPB テンプレートからの FAT イメージ作成、対象 FAT BPB を保持して完全バックアップを先に作成する 512 バイトの安全なブートコードインポート、仮想データ領域とフッターの検証後に編集可能な FAT セッションとして再度開ける独立した固定 VHD コピーを追加します。元の VHD は変更されず、動的 VHD はネイティブな書き込み対象になりません。

外部アダプターは明示的に扱います。`qemu-img` は VHDX、VMDK、QCOW2 用の任意アダプターであり、機能レポートとキャンセルを備えます。任意の `dmg2img` は DMG から新しい RAW HFS+ 出力を作成するだけで、DiskForge は DMG をマウントも書き込みもしません。新しい取得キューは、選択されたリムーバブルまたは光学メディアを読み取り、新規ファイルと SHA-256 監査記録を作成するだけで、デバイス書き込み機能は含みません。これらの新しい経路も国連の六つの作業言語と日本語に翻訳されています。公開ワークフローは `v*` タグだけを受け付け、タグとプロジェクトメタデータの一致を強制し、既存 Release がある場合は失敗します。バージョン付き資産は一切上書きされません。

## v0.10.0.dev0：安全な ISO 再構築と旧式 IMG/IMA フロッピー

現在の開発版では、**IMA** を単なる IMG の拡張子別名ではなく、第一級の RAW イメージ形式として扱います。デスクトップ、コマンドライン、グラフィカルなレシピデザイナー、バッチ実行器はいずれも `.ima` または `.img` 出力を明示的に選択できます。新規イメージ作成では、再オープン検証済みの FAT12 旧式フロッピープロファイルを提供します。DMF と 82 トラックを含む、一般的な PC 互換 5.25 インチ/3.5 インチの 160 KiB から 2.88 MiB までをカバーし、明示的なカスタム CHS ジオメトリも指定できます。有効な FAT IMA は FAT IMG と同じく、閲覧、内蔵プレビュー、注入、削除、名前変更、属性変更、抽出、ハッシュ、変換を行えます。

ISO の内容編集は常に別出力への再構築で実行され、ステージ済みファイルを検証して Rock Ridge/UDF プロファイルを維持します。検証済みの単一初期 El Torito ブートエントリも保持できます。複数セクション/複数ブートカタログ、ハイブリッドシステム領域、または曖昧なマッピングは明示的に拒否されます。バッチ v4 の `iso_edit` も同じ安全コアを使用します。

> 128/256 バイトセクター、GCR や可変セクター符号化、ハードセクター媒体、非 FAT ファイルシステム、コピー保護トラック、flux/bitcell キャプチャは、RAW バイトの保存、検査、ハッシュ、比較の対象にとどまります。DiskForge はこれらを安全にファイルレベル編集できる FAT イメージとは表明しません。

## 主な機能

DiskForge は実用的なイメージ管理の流れを一つの UI に統合します。メインウィンドウにはイメージエクスプローラー、ディレクトリ表、メタデータパネル、アクティビティログ、キャンセル可能な進捗表示があります。破壊的な操作は通常の閲覧操作から分離して表示されます。

| ワークフロー | ネイティブ機能 | 備考 |
|---|---|---|
| イメージ作成 | RAW/IMG/IMA、FAT12、FAT16、FAT32、検証済み旧式 FAT12 フロッピープロファイル、DMF レイアウト FAT12、ISO9660/Joliet/Rock Ridge/UDF、任意のクラシック HFS | 編集可能な FAT、明示的な IMG/IMA プロファイルまたは対応カスタム CHS、DMF、任意の El Torito ブートメディア付き ISO を作成できます。`hformat` が明示的に利用可能な場合、DiskForge は 800 KiB 以上の新しい独立したクラシック HFS 通常ファイルイメージを作成できます。HFS+ は読み取り専用のままです。 |
| 閲覧と抽出 | 検証済みの表示ラベルなし旧式 DOS フロッピーを含む FAT12/16/32、保守的な FAT12/FAT16 削除済みルートファイル候補、読み取り専用 IMD セクター検査、ISO9660/Joliet、安全な単一イメージ ZIP コンテナー、固定 VHD データビュー、任意の NTFS/EXT/クラシック HFS/HFS+ 読み取り専用バックエンド | 通常の ZIP は、安全なルートレベルのイメージペイロードがちょうど一つある場合だけ、自動削除されるプライベートな読み取り専用セッションに物化されます。書き込み可能または変換可能なイメージにはなりません。ツリーと表は決定的なページングと並べ替えキャッシュを使用します。検証済みの MBR/GPT パーティションは常に明示的な表インデックスで選択されます。FAT は既存の編集経路を維持し、NTFS/EXT/クラシック HFS/HFS+ は読み取り専用バックエンドで正確に検証されたオフセットにのみ開かれます。ダブルクリックすると、テキスト、画像、一般的なアーカイブ、旧式パッケージ、実行ファイル、バイナリデータ用の非実行文書ワークスペースが開きます。テキストは検索、コピー保存ができ、書き込み可能な FAT 項目だけ編集してイメージへ保存し戻せます。固定 VHD はフッターを除く一時 RAW 読み取り専用ビューで開きます。 |
| イメージディレクトリの棚卸し | JSON、CSV、HTML レポート付きの読み取り専用ローカルイメージメタデータ走査 | 一つのローカルディレクトリを任意で再帰走査し、既知のイメージ候補を拡張子、認識済み形式、ファイルシステム、バイト範囲、SHA-256 プレフィックスで絞り込めます。項目ごとの SHA-256 とパーティション概要は任意です。すべてのレポートは走査ルート外の新規ファイルであり、候補イメージは変更されません。 |
| 内容の変更 | FAT ファイル/フォルダーの注入、削除、名前変更、通常ファイルのディレクトリ間移動、時刻変更、安全な再構築式 ISO 編集、任意の制御済み NTFS/EXT/クラシック HFS 注入 | FAT IMG と IMA は同じ編集ワークフローを共有します。通常ファイルは既存ディレクトリへ上書きなしで移動できます。ルート、存在しないまたはディレクトリでない移動先、名前競合、読み取り専用セッション、およびすべてのディレクトリ移動は、イメージ変更前に拒否されます。同一ディレクトリ内の名前変更は別操作のままです。ISO 編集は常に新規イメージを出力し、内容を検証して Rock Ridge/UDF を維持します。検証済み単一初期 El Torito エントリのみ保持し、複数ブート、ハイブリッド、曖昧な構成は拒否します。`ntfsprogs`、`e2fsprogs`、または `hfsutils` が明示的に利用可能な場合、NTFS/EXT/クラシック HFS は検証済みの独立出力イメージのルートへ新しい通常ファイルだけを追加できます。元イメージ、パーティションオフセット、メタデータ、名前変更、削除、上書きは許可されません。クラシック HFS の注入は生データフォークだけを転送し、HFS+ は読み取り専用のままです。 |
| 形式変換 | RAW/IMG/IMA と固定 VHD をネイティブ変換 | IMG と IMA は明示的に選択した拡張子を保持します。VHDX、VMDK、QCOW2 は明示的に設定した `qemu-img` アダプターを使用します。 |
| FAT のコンパクト化 | 再構築方式のデフラグ | 元のイメージを保持したまま、新しいイメージを書き出します。 |
| 構造とブートの検査 | 512 バイトの 16 進ビュー/編集、FAT BPB、オリジナルテンプレート、中立 MBR と展開計画、末尾ゼロセクター、El Torito カタログ | テンプレートは BPB を保持し外部ブートコードを含みません。保護操作はバックアップを作成し、出力は新規ファイルです。 |
| 検証と自動化 | SHA-256、完全操作対応グラフィカルレシピスタジオ、事前計画、項目ごとの結果確認、JSON バッチ、監査可能なログ、ディレクトリレポート | スキーマ v4 は `iso_edit`、`ntfs_inject`、`ext_inject`、`hfs_inject`、`hfs_create`、`export_listing`、FAT の `move` を追加します。`export_listing` はローカルのテキスト/HTML レポートだけを作成し、明示的な読み取り専用パーティションを対象にできます。テキスト/HTML のディレクトリレポートは、閲覧可能なすべてのファイルシステムと明示的な読み取り専用パーティションに対して一つの安定した完全走査を使用します。デザイナーは変換、検証、比較、サイズ変更、注入、クラシック HFS 作成、抽出、コンテナー操作のレシピを作成、再読込、編集します。`--dry-run` は変更前に操作を確認し、無人バッチは物理デバイスへの書き込みを拒否します。 |
| 再配布用アーカイブ | 認証付き `.dfb` コンテナーと SHA-256 検証付き複数イメージ自己展開 `.pyz` | `.dfb` は任意の AES-256-GCM 暗号化、圧縮、コメント、項目ごとの検証に対応します。各ネイティブパッケージには、受信側で Python を事前インストールせずに `.pyz` ペイロードを検証・抽出できる独立した `DiskForgeExtractor` も含まれます。 |
| 物理メディアの読書き | ストリーミングによる取得と復元 | システムディスク、マウント済みターゲット、容量不一致を拒否し、入力確認を求めます。検出された光学メディアは読み取り専用で、既定で ISO に出力されます。 |
| 低レベルフロッピーフォーマット | Linux コントローラーフロッピーおよび検出済み UFI USB フロッピーバックエンド | `fdformat` は標準コントローラーノードに限定されます。UFI USB 候補は sysfs によりリムーバブルメディアへ関連付けられ、`ufiformat -i` で識別され、報告された容量を明示選択して `FORMAT_FLOPPY` を入力する必要があります。常に `-V` で検証します。FAT 作成は再確認を要する別操作であり、各ドライブモデルには実機受入試験が必要です。 |

## 安全性を最優先

> ディスクイメージツールでは、危険な操作を**誤って実行しにくくする**べきです。

DiskForge はイメージを自動マウントせず、物理デバイスへ自動書き込みもしません。FAT 展開では、まず確認可能な中立 MBR イメージを作成し、物理書き込み保護を迂回しません。書き込み前に容量、マウント状態、システムディスクを確認し、正確に `ERASE` と入力する必要があります。完了後にバイト検証も可能です。ブートセクター変更の前にはイメージ全体のバックアップも作成されます。重要なメディアを扱う前に、必ず使い捨てのテストイメージで操作を確認してください。

## 可搬設定

`diskforge --portable` では、言語、テーマ、フォント、最近使ったイメージ、表示、外部ツールパスを現在のディレクトリの `DiskForgeData/diskforge.ini` に保存します。`--portable=DIR`、`--portable-directory DIR`、または `DISKFORGE_PORTABLE_DIR` で場所を指定できます。このモードは通常の INI を使用し、システムレジストリを必要としません。

## すぐに始める

### ソースから起動

```bash
python -m pip install -e '.[dev]'
diskforge
```

### コマンドライン

```bash
diskforge-cli create-fat demo.img --size-mib 32 --fat 16
diskforge-cli info demo.img
diskforge-cli list demo.img
diskforge-cli list partitioned.img --partition 2
diskforge-cli export-listing partitioned.img partition-report.html --html --partition 2
diskforge-cli move-fat demo.img /README.TXT /DOCS  # /DOCS は既存である必要があります。通常ファイルのみ
diskforge-cli list archived-image.zip  # 安全なルートレベルのイメージペイロード一つのみ。読み取り専用
diskforge-cli list-deleted-fat demo.img  # FAT12/FAT16 固定ルートの 8.3 候補のみ
diskforge-cli recover-deleted-fat demo.img 17 recovered.bin  # 新規ローカル出力。demo.img は決して書き換えません
diskforge-cli imd-info legacy.imd  # 読み取り専用のトラック/セクター監査
diskforge-cli convert-imd legacy.imd exported.img  # 証明済みの矩形通常データレイアウトのみ
diskforge-cli inventory-images ./image-library image-library-report.json --recursive --include-sha256  # 読み取り専用。レポートは走査ルート外に必要です
diskforge-cli create-iso folder bootable.iso --boot-image boot.img --boot-media noemul
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

### ネイティブパッケージを構築

```bash
python scripts/build.py
```

対応するネイティブアプリは、それぞれの対象 OS 上で構築してください。リポジトリのワークフローでは四つのリリースターゲットを自動構築します。

## 形式の対応状況

| 形式またはファイルシステム | 検査 | 閲覧 / 変更 | 作成 / 変換 |
|---|---:|---:|---:|
| RAW / IMG / IMA / BIN | 対応 | FAT ペイロード | 対応 |
| IMD | 読み取り専用トラック/セクター検査 | 直接ファイルシステム編集は不可。完全な矩形 CHS と通常データを証明した場合だけ新しい RAW を厳格に出力します。 | IMD 作成・インプレース変換は非対応。 |
| FAT12 / FAT16 / FAT32 | 対応 | FAT は編集可能なままです。FAT12/FAT16 では保守的な固定ルートの削除済み 8.3 候補も扱えます。復元は現在空いている単一クラスターだけを新しいローカルファイルへコピーします。 | 対応 |
| ISO9660 / Joliet | 対応 | 読み取り・抽出 | フォルダーから作成 |
| 固定 VHD | 対応 | 一時読み取り専用データビューと変換 | 対応 |
| VHDX / VMDK / QCOW2 | アダプター設定時 | 変換ワークフロー経由 | アダプター設定時 |
| NTFS / EXT2 / EXT3 / EXT4 | シグネチャまたはパーティション情報 | 任意の Sleuth Kit による offset-0 または明示選択した検証済み MBR/GPT パーティションでの読み取り/一覧/抽出。テキスト/HTML のディレクトリレポートも利用可能です。設定済み `ntfsprogs` / `e2fsprogs` による制御済み注入は引き続き独立した offset-0 の新規出力に限定されます。 | 閲覧は読み取り専用です。注入は外部バックエンド限定：offset-0 の独立ボリューム、ルートの新規通常ファイル、上書き拒否。元の SHA-256、読み戻し SHA-256、ファイルシステム検証が必須です。 |
| HFS / HFS+ | シグネチャまたはパーティション情報 | 任意の Sleuth Kit による offset-0 または明示選択した検証済み MBR/GPT パーティションでの読み取り/一覧/データフォーク抽出。テキスト/HTML のディレクトリレポートも利用可能です。クラシック HFS は設定済み `hfsutils` により新規出力への制御済み注入と、検証済みの新規通常ファイルイメージ作成も可能です。 | パーティション閲覧は読み取り専用です。クラシック HFS 作成は新規通常ファイル、512 バイト単位で 800 KiB 以上、安全な 1～27 文字の ASCII ボリュームラベルに限定され、デバイス、パーティションマップ、既存出力、`-f` は拒否されます。原子的な昇格前に HFS シグネチャと SHA-256 を検証します。注入は引き続き offset-0 の独立ボリューム、ルートの安全な新規通常ファイル、生データフォークのみ、上書き拒否に限定され、元と各読み戻しペイロードの SHA-256 が必須です。HFS+ は読み取り専用のままで、ジャーナル付き HFS+ 書き込み、リソースフォーク再構築、ファイルシステム修復は非対応です。 |
| 単一イメージ ZIP コンテナー（`.zip`） | ZIP 構造と一つの候補ペイロード | 自動削除される一時物化後の読み取り/一覧/抽出/レポートのみ | 作成、変換、ファイルシステム編集、アーカイブ書き込みは不可。ルートレベルで暗号化されていない Stored/Deflated の `.img`、`.ima`、`.bin`、`.dd`、`.dmf`、`.iso`、`.hfs` のいずれか一つ（2 GiB 以下）で、閲覧可能なイメージとして再認識される必要があります。 |
| DMG | シグネチャ情報 | ネイティブ変更なし | 互換性のある外部ワークフローを使用。 |

DiskForge は、未対応の編集パスを隠したり安全でない書き込みを試みたりしません。バッチイメージ棚卸しはローカルの読み取り専用レポートワークフローであり、フォレンジックスキャナーや無人の変更ではありません。既存の非シンボリックリンクディレクトリ一つだけを受け付け、リンクを無視し、既知のイメージ拡張子だけを認識し、通常ファイルは最大 10,000 件、16 GiB を超えるファイルは除外し、走査ルート外に新しい JSON/CSV/HTML レポートだけを書き出します。イメージをマウントせず、物理デバイスを検査せず、レポートを上書きせず、バッチスキーマ v4 にも入りません。IMD はフロッピーのセクターコンテナーとして検査され、RAW または書き込み可能なファイルシステムとして自動的には扱われません。固定セクター数/サイズ、連続する `1..N` 識別子、任意マップなし、通常（通常の圧縮フィルを含む）セクターデータを持つ完全な矩形 CHS レイアウトだけから、新しい RAW を出力できます。不規則ジオメトリ、欠落/削除/不良セクター、可変レイアウト、重複記録、マップ、末尾バイト、デバイス出力、上書き、IMD 書き込み、およびビットストリーム/磁束に関する主張は拒否されます。FAT 削除済みファイルの復元は、汎用フォレンジック復元ではなく限定された**候補コピー**ワークフローです。FAT12/FAT16 の固定ルートにある通常の 8.3 スロットで、正の長さが一つのクラスター以下、開始クラスターが現在空いている候補だけを受け付けます。削除済み名前の先頭文字は取得できず、候補バイトは古いか上書き済みの場合があるため、元の名前や完全性は保証しません。FAT32、サブディレクトリ、長い名前、ゼロ長または複数クラスターのチェーン、使用中クラスター、元イメージ書き込み、既存出力の上書き、デバイス復元、バッチ復元は拒否されます。通常の ZIP は限定された**読み取り専用単一イメージコンテナー**であり、汎用ファイルシステムや変換元ではありません。承認済みの直接イメージ拡張子を持つ安全なルートレベル、非暗号化、Stored/Deflated の 2 GiB 以下のペイロードがちょうど一つ必要です。複数項目、フォルダー、危険な名前、暗号化、未知の圧縮、空/過大/未知のペイロード、再帰コンテナー、仮想ディスクチェーン、変換、およびすべての ZIP 書き込みは拒否されます。一時バイトは通常のクローズ、エラー、キャンセル時に削除されます。FAT の移動は、一つの通常ファイルを既存の移動先ディレクトリへ移す場合に意図的に限定されます。項目の上書きや統合は行わず、利用可能な汎用ディレクトリ実装はアトミックではなくコピー後に削除するため、ディレクトリ移動は拒否されます。 仮想ディスクの変換には **Tools → Preferences** で `qemu-img` を設定してください。NTFS/EXT/HFS/HFS+ の読み取り専用閲覧にはローカルの Sleuth Kit `fls` と `icat` が必要で、任意の制御済み注入には明示設定された `ntfscp`/`ntfsls`/`ntfscat`、`debugfs`/`e2fsck`、またはクラシック HFS 専用の注入用 `hmount`/`hcopy`/`hls`、検証済み作成用 `hformat` が必要です。アプリケーションが外部ツールを黙ってダウンロード、マウント、実行することはありません。詳細は [FILESYSTEM_INJECTION.md](docs/FILESYSTEM_INJECTION.md) を参照してください。

## 品質とビルド

FAT の作成、安全な通常ファイル移動、安全な単一イメージ ZIP の物化とクリーンアップ、保守的な FAT 削除済み候補復元、読み取り専用 IMD 検査と厳格 RAW エクスポート、読み取り専用バッチイメージ棚卸しの絞り込みと JSON/CSV/HTML レポート、編集、起動 ISO と El Torito、オリジナルテンプレートの BPB 保持とバックアップ、一時 VHD 閲覧、展開計画、ゼロ末尾レポート、ドラッグ＆ドロップ、完全なバッチレシピ編集と事前検証、文書プレビュー/検索/保存し戻し、ページングされたディレクトリ走査、七言語の完全ワークスペース、公開 API、可搬設定、タスクセンター、フォント、クロスプラットフォームの光学メディア認識、デバイス書き込み保護、FAT 再構築を自動テストしています。pytest は厳格な設定を使い、警告をエラーとして扱います。GUI はオフスクリーン環境でも検証されます。CI は Windows、Linux、macOS Intel、macOS Apple Silicon でテストを実行し、各ネイティブターゲットをパッケージ化します。タグはメタデータと照合され、既存 Release があると資産を上書きせずワークフローが停止します。

```bash
QT_QPA_PLATFORM=offscreen pytest
QT_QPA_PLATFORM=offscreen python scripts/gui_smoke.py
```

構築とリリースの詳細は [BUILDING.md](docs/BUILDING.md)、実ファイルシステムと UFI ハードウェアの任意受入手順は [VALIDATION.md](docs/VALIDATION.md) を参照してください。GUI スモークテストの記録は [gui_validation.md](artifacts/gui_validation.md) にあります。

## コントリビューション

Issue と Pull Request を歓迎します。変更は目的を絞り、動作変更には回帰テストを追加し、実際のディスクイメージ、認証情報、プライベートパス、生成済みビルド出力をコミットしないでください。

## ライセンス

DiskForge は [MIT License](LICENSE) で公開されています。
