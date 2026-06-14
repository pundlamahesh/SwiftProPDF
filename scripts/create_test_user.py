from pathlib import Path
from SwiftProPDF.auth import init_db, create_user

EMAIL = "admin@example.com"
PASSWORD = "Admin@12345"


def main():
    db_path = Path("src/SwiftProPDF/instance/swiftpropdf.sqlite3")
    init_db(db_path)
    try:
        uid = create_user(db_path, "Admin", "User", EMAIL, PASSWORD)
        print("CREATED", uid)
    except Exception as e:
        print("ERROR", e)

if __name__ == '__main__':
    main()
