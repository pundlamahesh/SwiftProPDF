from pathlib import Path
from SwiftProPDF.auth import (
    get_user_by_email,
    create_user_with_role,
    set_user_role,
    init_db,
)

DB_PATH = Path("src/SwiftProPDF/instance/swiftpropdf.sqlite3")
init_db(DB_PATH)

email = "pundlamahesh@gmail.com"
user = get_user_by_email(DB_PATH, email)
if user:
    set_user_role(DB_PATH, user["id"], "ADMIN")
    print(f"Promoted existing user id={user['id']} email={email} to ADMIN")
else:
    pwd = "ChangeMe!234"
    uid = create_user_with_role(DB_PATH, "Admin", "User", email, pwd, "ADMIN")
    print(f"Created ADMIN user id={uid} email={email} with password={pwd}")
