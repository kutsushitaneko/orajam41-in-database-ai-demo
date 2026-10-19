# Agent専用プロファイルの実機検証

## 変更内容

`OJ41_BUSINESS_AI`からNL2SQL用の`object_list`と`enforce_object_list`を除いた。Agentが呼ぶのは、固定SQLを実行する2つのPL/SQLツールであり、NL2SQLや組み込みSQLツールは使っていない。閲覧範囲は各ツールが参照するビューと、チケット・保守登録番号の検査で制限する。

設定する属性は`provider`、`credential_name`、`region`、`model`、`oci_compartment_id`、`temperature`、`max_tokens`の7個。接続はリソースプリンシパル、モデルは`xai.grok-4.3`、リージョンはus-chicago-1。Agent専用の属性生成処理を設け、NL2SQLの設定を持つ接続確認用の関数を流用しないようにした。

準備処理はデモ専用の`OJ41_BUSINESS_AI`を再作成する。属性の追加・上書きだけでは、以前の設定が残るため。準備処理はデモ実行中には行わない。データや埋め込みモデルは再作成していない。

## 確認方法

```powershell
uv run --locked python -m webinar_demo.business_ai --setup
uv run --locked python -m webinar_demo.evaluate_stage4 --agents-only --output local/agent-profile-evaluation.json
```

設定済みの属性名は、次のSQLで確認できる。

```sql
SELECT attribute_name
FROM user_cloud_ai_profile_attributes
WHERE profile_name = 'OJ41_BUSINESS_AI'
ORDER BY attribute_name;
```

SQLクライアント用の動作確認には[03_support_agent.sql](../sql/demos/03_support_agent.sql)を使う。プロファイル作成例は[64_business_ai_template.sql](../sql/setup/64_business_ai_template.sql)、準備処理は[business_ai.py](../src/webinar_demo/business_ai.py)を参照。

## 結果

2026年10月19日、既存のAutonomous AI Database 26ai環境で確認した。

| 確認対象 | 結果 |
|---|---|
| Agentプロファイル | 上記7属性のみ。object_list・enforce_object_list・object_list_modeの登録なし |
| NL2SQL用プロファイル | BASELINE・TUNEDとも更新前後で属性が一致 |
| 固定SQLの契約ツール | 9ケース、別顧客の番号拒否、引数の差し替え拒否、呼び出し上限が正常 |
| SR001／DEV001：有効な現地保守 | 根拠付き回答、onsite_eligible=Y |
| SR001／DEV002：期限切れ | 根拠付き回答、onsite_eligible=N |
| SR001／DEV004：リモート保守のみ | 根拠付き回答、onsite_eligible=N |
| SR002／DEV009：別顧客のチケット | 当該顧客の根拠付き回答、onsite_eligible=Y |
| SR001／DEV001：根拠のないE999 | 根拠不足として処理。契約値はYのまま保持 |
| SQLクライアント用スクリプト | 03_support_agent.sqlをドライバー経由で実行。回答・引用の照合、両ツールの履歴、チケットの消去が正常 |
| ローカルテスト | 80件成功、実DBを別途必要とする5件はスキップ |

5つのAgentケースはいずれも、両ツール各1回の実行、返却データ、引用、標準履歴との対応を既存の検証器で確認した。所要時間は1件あたり約14〜23秒だった。これは今回の実行結果であり、LLMの応答や所要時間が毎回同じになる保証ではない。

SQLスクリプトの検証は実DBに対するドライバー経由の実行であり、VS Code SQL Developerの画面操作を再確認したものではない。結果は`local/agent-profile-evaluation.json`、`local/agent-profile-sql-check.json`、設定確認は`local/agent-profile-check.json`に保存した。環境固有の設定値を含むバックアップは公開していない。
