from pathlib import Path

from SwiftProPDF.auth import init_db, list_users
from SwiftProPDF.database import connect


DB_PATH = Path("src/SwiftProPDF/instance/swiftpropdf.sqlite3")
init_db(DB_PATH)
with connect(DB_PATH) as conn:
    conn.execute('UPDATE users SET role = UPPER(role) WHERE role IS NOT NULL')
    conn.execute('UPDATE users SET plan_type = UPPER(plan_type) WHERE plan_type IS NOT NULL')
    conn.execute("UPDATE users SET role = 'ADMIN' WHERE role = 'admin'")

print('Roles normalized')

for u in list_users(DB_PATH):
    print(u['id'], u['email'], u['role'], 'is_admin=', u['is_admin'])
