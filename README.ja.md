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
| Windows x64 | `DiskForge-v0.6.0-windows-x64.zip` | 展開して `DiskForge.exe` を実行します。 |
| Linux x64 | `DiskForge-v0.6.0-linux-x64.zip` | 展開して `./DiskForge` を実行します。 |
| macOS Intel | `DiskForge-v0.6.0-macos-intel-x64.zip` | 展開し、`DiskForge.app` を Applications に移動します。 |
| macOS Apple Silicon | `DiskForge-v0.6.0-macos-arm64.zip` | 展開し、`DiskForge.app` を Applications に移動します。 |

## v0.6.0 の統合機能

v0.6.0 は、ブート作成、展開計画、仮想ディスク閲覧、自動化の事前検証、可搬設定、タスク履歴を一つに統合します。ローカルフォルダーと任意のローカルブートイメージから El Torito ISO を作成でき、元のブートファイルは変更されません。ブートセクターには FAT BPB を保持して完全バックアップを作成する、オリジナルの中立停止/メッセージテンプレートがあります。固定 VHD は一時 RAW データビューで読み取り専用に閲覧し、閉じると自動消去されます。FAT 展開はまず確認可能な中立 MBR イメージを作り、物理書き込みの `ERASE` 保護を迂回しません。バッチには `--dry-run` が追加され、デスクトップは実行前に計画を表示します。タスクセンターは待機、実行、完了、失敗、キャンセルを示し、可搬モードは INI に設定を保存します。pytest は警告をエラーとして扱い続けます。

## 主な機能

DiskForge は実用的なイメージ管理の流れを一つの UI に統合します。メインウィンドウにはイメージエクスプローラー、ディレクトリ表、メタデータパネル、アクティビティログ、キャンセル可能な進捗表示があります。破壊的な操作は通常の閲覧操作から分離して表示されます。

| ワークフロー | ネイティブ機能 | 備考 |
|---|---|---|
| イメージ作成 | RAW/IMG、FAT12、FAT16、FAT32、DMF レイアウト FAT12、ISO9660/Joliet | 編集可能な FAT、文書化された DMF、通常 ISO、またはローカルフォルダーと任意のブートイメージから El Torito ISO を作成できます。 |
| 閲覧と抽出 | FAT12/16/32、ISO9660/Joliet、固定 VHD データビュー | ツリービュー、並べ替え可能な詳細表、保持されるアイコングリッド、安全なダブルクリック・プレビュー、一括抽出、MBR/GPT 検査。固定 VHD はフッターを除く一時 RAW 読み取り専用ビューで開きます。 |
| 内容の変更 | FAT ファイル/フォルダーの注入、削除、時刻変更 | ローカルのファイルまたはフォルダーを編集可能な FAT イメージへ、表示中の対象フォルダー上にも直接ドラッグできます。ISO は読み取り専用です。 |
| 形式変換 | RAW/IMG と固定 VHD をネイティブ変換 | VHDX、VMDK、QCOW2 は明示的に設定した `qemu-img` アダプターを使用します。 |
| FAT のコンパクト化 | 再構築方式のデフラグ | 元のイメージを保持したまま、新しいイメージを書き出します。 |
| 構造とブートの検査 | 512 バイトの 16 進ビュー/編集、FAT BPB、オリジナルテンプレート、中立 MBR と展開計画、末尾ゼロセクター、El Torito カタログ | テンプレートは BPB を保持し外部ブートコードを含みません。保護操作はバックアップを作成し、出力は新規ファイルです。 |
| 検証と自動化 | SHA-256、グラフィカルデザイナー、事前計画、JSON バッチ、監査可能なログ | `--dry-run` は変更前に操作を確認し、無人バッチは物理デバイスへの書き込みを拒否します。 |
| 再配布用アーカイブ | 認証付き `.dfb` コンテナーと SHA-256 検証付き複数イメージ自己展開 `.pyz` | `.dfb` は任意の AES-256-GCM 暗号化、圧縮、コメント、項目ごとの検証に対応します。 |
| 物理メディアの読書き | ストリーミングによる取得と復元 | システムディスク、マウント済みターゲット、容量不一致を拒否し、入力確認を求めます。検出された光学メディアは読み取り専用で、既定で ISO に出力されます。 |

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
diskforge-cli create-iso folder bootable.iso --boot-image boot.img --boot-media noemul
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
| FAT12 / FAT16 / FAT32 | 対応 | 対応 | 対応 |
| ISO9660 / Joliet | 対応 | 読み取り・抽出 | フォルダーから作成 |
| 固定 VHD | 対応 | 一時読み取り専用データビューと変換 | 対応 |
| VHDX / VMDK / QCOW2 | アダプター設定時 | 変換ワークフロー経由 | アダプター設定時 |
| NTFS / EXT / DMG | シグネチャまたはパーティション情報 | ネイティブ変更なし | 互換性のある外部ワークフローを使用 |

DiskForge は、未対応の編集パスを隠したり安全でない書き込みを試みたりしません。仮想ディスクの変換には **Tools → Preferences** で `qemu-img` を設定してください。アプリケーションが外部コンバーターを黙ってダウンロードまたは実行することはありません。

## 品質とビルド

FAT の作成と編集、起動 ISO と El Torito、オリジナルテンプレートの BPB 保持とバックアップ、一時 VHD 閲覧、展開計画、ゼロ末尾レポート、ドラッグ＆ドロップ、バッチ設計と事前検証、公開 API、可搬設定、タスクセンター、フォント、デバイス書き込み保護、FAT 再構築を自動テストしています。GUI はオフスクリーン環境でも検証されます。CI は Windows、Linux、macOS Intel、macOS Apple Silicon でテストを実行し、各ネイティブターゲットをパッケージ化します。

```bash
QT_QPA_PLATFORM=offscreen pytest
QT_QPA_PLATFORM=offscreen python scripts/gui_smoke.py
```

構築とリリースの詳細は [BUILDING.md](docs/BUILDING.md) を参照してください。GUI スモークテストの記録は [gui_validation.md](artifacts/gui_validation.md) にあります。

## コントリビューション

Issue と Pull Request を歓迎します。変更は目的を絞り、動作変更には回帰テストを追加し、実際のディスクイメージ、認証情報、プライベートパス、生成済みビルド出力をコミットしないでください。

## ライセンス

DiskForge は [MIT License](LICENSE) で公開されています。
