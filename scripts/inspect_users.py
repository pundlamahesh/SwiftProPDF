from pathlib import Path

from SwiftProPDF.auth import init_db, list_users


db_path = Path("src/SwiftProPDF/instance/swiftpropdf.sqlite3")
init_db(db_path)
users = list_users(db_path)
print(len(users))
for user in users:
    print({
        "id": user["id"],
        "first_name": user["first_name"],
        "last_name": user["last_name"],
        "email": user["email"],
        "role": user["role"],
    })
