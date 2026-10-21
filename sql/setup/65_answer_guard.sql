CREATE OR REPLACE PACKAGE OJ41_ANSWER_GUARD AUTHID CURRENT_USER AS
  -- Validation checks evidence against successful history and source quotes.
  -- Free-text commitment warnings are advisory; semantic review remains required.
  FUNCTION validate_json(p_answer CLOB, p_documents CLOB) RETURN CLOB;
  FUNCTION validate_agent(p_answer CLOB, p_trace CLOB, p_run_id VARCHAR2) RETURN CLOB;
  PROCEDURE print_clob(p_text CLOB);
END;
/
