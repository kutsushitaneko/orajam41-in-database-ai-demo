CREATE OR REPLACE PACKAGE OJ41_RAG AUTHID CURRENT_USER AS
  -- Owns ticket lifecycle; call as a PL/SQL block, not inside a SQL query.
  FUNCTION answer_question(p_case_id VARCHAR2,p_question VARCHAR2,
    p_device VARCHAR2 DEFAULT NULL,p_model VARCHAR2 DEFAULT NULL) RETURN CLOB;
END;
/
