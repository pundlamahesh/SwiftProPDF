import sqlite3
from pathlib import Path

db = Path('src/SwiftPDF/instance/swiftpdf.sqlite3')
con = sqlite3.connect(db)
con.row_factory = sqlite3.Row
rows = con.execute('SELECT id, first_name, last_name, email FROM users').fetchall()
print(len(rows))
for r in rows:
    print(dict(r))
con.close()
