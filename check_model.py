import sqlite3
from server.pull import pick_passages, build_prompt, SYSTEM_PROMPT
from server.llm import complete, parse_claims

conn = sqlite3.connect("data/server.db")
conn.row_factory = sqlite3.Row
rows = conn.execute(
    "SELECT c.id, c.page, c.text, d.label FROM chunks c "
    "JOIN documents d ON d.id = c.document_id "
    "WHERE c.ticker = 'INFY' AND c.doc_type = 'transcript'"
).fetchall()
chunks = [dict(r) for r in rows]
passages = pick_passages(chunks)
print("chunks stored:", len(chunks))
print("passages sent:", len(passages))
reply = complete(SYSTEM_PROMPT, build_prompt(passages))
print("RAW REPLY:")
print(reply)
print("PARSED:", parse_claims(reply))

