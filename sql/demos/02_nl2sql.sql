-- Use the same connection for case selection and all SELECTs.
-- Database Actions: run this whole file as ONE script.
-- Execute reviewed generated SQL in a NEW script containing open_case + SELECT + clear_case.
BEGIN OJ41_CASE_CTX.open_case('SR001'); END;
/

-- C1: object_list=[{"owner":"ORAJAM41USER"}], comments=false. Display only.
-- Both profiles omit object_list_mode (default all) and enforce_object_list.
SELECT DBMS_CLOUD_AI.GENERATE(
  prompt=>'この受付案件の顧客について、基準日時点で現地保守の対象となるサーバーの保守登録番号を昇順で教えてください。',
  profile_name=>'OJ41_NL2SQL_BASELINE',action=>'showsql') AS generated_sql
FROM dual;

-- C2: SAME question and SAME owner-only object_list; only comments=true differs.
SELECT DBMS_CLOUD_AI.GENERATE(
  prompt=>'この受付案件の顧客について、基準日時点で現地保守の対象となるサーバーの保守登録番号を昇順で教えてください。',
  profile_name=>'OJ41_NL2SQL_TUNED',action=>'showsql') AS generated_sql
FROM dual;

-- C2の正解SQL：照合対象はこのSELECTのみ。
-- C2で生成されたSQLを実行した結果が、DEV001, DEV005, DEV006, DEV008の4行になること。
SELECT device_id FROM OJ41_VISIBLE_CONTRACTS WHERE onsite_eligible='Y' ORDER BY device_id;

-- 以下の3文はビューの補助確認。C2の別解ではなく、生成SQLとの一致は求めない。
-- 機種別の現地保守対象件数：AX-100=3、BX-200=1。
SELECT model,COUNT(*) FROM OJ41_VISIBLE_CONTRACTS WHERE onsite_eligible='Y' GROUP BY model ORDER BY model;
-- 非有効契約：DEV002, DEV003, DEV007。
SELECT device_id FROM OJ41_VISIBLE_CONTRACTS WHERE is_active='N' ORDER BY device_id;
-- 別顧客のサーバー：DEV009はSR001の範囲外なので0行。
SELECT device_id,contract_id FROM OJ41_VISIBLE_CONTRACTS WHERE device_id='DEV009';

BEGIN OJ41_CASE_CTX.clear_case; END;
/
