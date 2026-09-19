# 全6関節XL430静止組立 study

2026-09-19に受領した`low_cost_robot_all_XL430_CAD_20260919.zip`を、リポジトリの元STEPから再生成・再検証するstudyです。

受領物は、混在サーボ構成の形状改訂を基準に、元の4台のXL330サブアセンブリを、元STEP内にあるXL430サブアセンブリ形状へ剛体置換していました。本studyは固定された`/mnt/data/...`への依存と要素番号範囲による削除を廃止し、SHA-256で保護された元STEPとアセンブリパスから再生成します。

## 現在の判定

**未承認です。印刷・製造用に使用しません。**

- 6台のXL430構成と217末端要素への再構成は再現できた。
- 流用された7部品のSTEP/STLは、単一ソリッド・閉じたメッシュとして有効。
- ただし、置換後の組立STEPを直接検査すると、静止姿勢に外部部品間の体積干渉が54件、最大約9,608.8 mm³残る。
- 同一モーター参照形状の内部重複168件は別集計であり、外部干渉には含めない。
- 受領ZIPの干渉レポートは置換前の混在サーボ基準モデルに対するもので、全XL430置換後の組立検査ではない。
- 受領ZIPに「72穴軸」を裏付ける全XL430置換後の測定レポートはない。収録されているのは混在版の5締結パターン・18軸の検査結果である。

生成STEPは`outputs/all_xl430_revision/unaccepted/<run-id>/`へ隔離し、`accepted/`へ昇格しません。`source/study.py print-package`と`prepare_print_package.py`は、保存済みレポートを信用せず検証を毎回再実行し、外部干渉や未実施の工学検証が残る限り終了コード2で停止して印刷物を生成しません。

## 再生成と確認

```bash
cd skills/cad-reverse-parametric
rtk uv run python studies/all_xl430_revision/source/study.py rebuild --run-id current
rtk uv run python studies/all_xl430_revision/source/study.py validate --run-id current
rtk uv run python studies/all_xl430_revision/source/study.py print-package \
  --run-id current --output /tmp/all_xl430_print.zip
rtk uv run pytest -q studies/all_xl430_revision/source/test_all_xl430.py
```

- `rebuild`は生成と検証を別プロセスで実行し、候補を`outputs/all_xl430_revision/unaccepted/<run-id>/`にだけ書き出す。
- B-repスキャンは151ソリッド・381候補ペアを検査するため約11分かかる。ワーカーのタイムアウトも印刷を止める側に倒れる。
- `print-package`は毎回`validate`をやり直してから判定する。現在は終了コード2で停止する。
- 検証記録は`outputs/all_xl430_revision/unaccepted/current/reports/`の`validation.json`、`collisions.json`、`external_collision_pairs.csv`に残る。

## 次に必要なCAD作業

1. 各XL430の取付基準面・軸・ねじスタックを定義する。
2. 7部品のうち、XL430外形と衝突するブラケット、リンク、グリッパーを局所変更する。
3. 全XL430置換後に穴軸と締結を再測定し、基準姿勢の物理干渉を0件にする。
4. 離散姿勢だけでなく、関節間を補間した連続経路で掃引干渉を検査する。
5. その後に初めてOrcaSlicer用パッケージを生成する。

メッシュが印刷可能であること、モーター数が6台であること、静止STEPが開けることは、全XL430アームとして組み立て可能であることの証明ではありません。
