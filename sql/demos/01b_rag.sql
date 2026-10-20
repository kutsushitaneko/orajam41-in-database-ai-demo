-- VS Code SQL Developer: enable DBMS Output and run each complete block.
-- Prerequisites: setup 65-68 and OJ41_BUSINESS_AI (setup 64).
DECLARE r CLOB;
BEGIN
  r:=OJ41_RAG.answer_question('SR001','DEV001の管理画面が開かない。最初に何を確認する？');
  OJ41_ANSWER_GUARD.print_clob(r);
END;
/

DECLARE r CLOB;
BEGIN
  r:=OJ41_RAG.answer_question('SR001','AX-100のE999の修理方法は？');
  OJ41_ANSWER_GUARD.print_clob(r);
END;
/

DECLARE r CLOB;
BEGIN
  r:=OJ41_RAG.answer_question('SR001','AX-100の保証延長料金を日本円で教えて。');
  OJ41_ANSWER_GUARD.print_clob(r);
END;
/
