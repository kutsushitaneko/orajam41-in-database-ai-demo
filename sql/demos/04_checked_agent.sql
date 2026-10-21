-- Optional reference, not part of the webinar demonstration.
-- Prerequisites: setup 60-68,80-81 and AI definitions from 64.
DECLARE r CLOB;
BEGIN
  r:=OJ41_CHECKED_AGENT.run('SR001','DEV001',
    '管理画面が開かない。最初に何を確認し、誰へ連絡すればよいですか。現地保守を頼めますか。');
  OJ41_ANSWER_GUARD.print_clob(r);
END;
/
