from SwiftProPDF.web_app.app import create_app


def test_login_page_offers_guest_home_link() -> None:
    app = create_app()

    response = app.test_client().get("/login")

    assert response.status_code == 200
    html = response.get_data(as_text=True)
    assert "Login as Guest" in html
    assert 'href="/"' in html
