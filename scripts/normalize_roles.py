from pathlib import Path
import sqlite3
DB=Path('src/SwiftPDF/instance/swiftpdf.sqlite3')
with sqlite3.connect(DB) as conn:
    conn.execute('UPDATE users SET role = UPPER(role) WHERE role IS NOT NULL')
    conn.execute('UPDATE users SET plan_type = UPPER(plan_type) WHERE plan_type IS NOT NULL')
    conn.execute("UPDATE users SET role = 'ADMIN' WHERE role = 'admin'")
    conn.commit()

print('Roles normalized')

from SwiftPDF.auth import list_users
for u in list_users(DB):
    print(u['id'], u['email'], u['role'], 'is_admin=', u['is_admin'])
