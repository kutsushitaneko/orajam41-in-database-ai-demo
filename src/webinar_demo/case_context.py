"""Explicit support-case scope for one request; no end-user authentication."""
from contextlib import contextmanager


def current_case(conn):
    with conn.cursor() as cur:
        cur.execute("SELECT OJ41_CASE_CTX.current_case(), OJ41_CASE_CTX.customer_id() FROM dual")
        case_id, customer_id = cur.fetchone()
    return dict(case_id=case_id, customer_id=customer_id)


def require_case(conn):
    context = current_case(conn)
    if not context["case_id"] or not context["customer_id"]:
        raise ValueError("受付案件を選択してください。")
    return context


@contextmanager
def case_scope(conn, case_id):
    """Use at the request boundary, never nest or invoke from an LLM tool."""
    try:
        with conn.cursor() as cur:
            cur.execute("BEGIN OJ41_CASE_CTX.open_case(:c); END;", c=case_id)
        yield require_case(conn)
    finally:
        with conn.cursor() as cur:
            cur.execute("BEGIN OJ41_CASE_CTX.clear_case; END;")
