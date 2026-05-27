from pathlib import Path
from SwiftPDF.auth import init_db, create_user

EMAIL = "admin@example.com"
PASSWORD = "Admin@12345"


def main():
    db = Path("src/SwiftPDF/instance/swiftpdf.sqlite3")
    init_db(db)
    try:
        uid = create_user(db, "Admin", "User", EMAIL, PASSWORD)
        print("CREATED", uid)
    except Exception as e:
        print("ERROR", e)

if __name__ == '__main__':
    main()
