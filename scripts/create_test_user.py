from pathlib import Path
from SwiftPDF.auth import init_db, create_user

def main():
    db = Path("src/SwiftPDF/instance/swiftpdf.sqlite3")
    init_db(db)
    try:
        uid = create_user(db, "Test", "User", "test@example.com", "password123")
        print("CREATED", uid)
    except Exception as e:
        print("ERROR", e)

if __name__ == '__main__':
    main()
