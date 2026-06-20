from SwiftProPDF.web_app.app import create_app


def test_robots_txt_is_served_from_site_root() -> None:
    app = create_app()

    response = app.test_client().get("/robots.txt")

    assert response.status_code == 200
    assert response.mimetype == "text/plain"
    assert "Sitemap: https://swiftpropdf.com/sitemap.xml" in response.get_data(as_text=True)


def test_sitemap_xml_is_served_from_site_root() -> None:
    app = create_app()

    response = app.test_client().get("/sitemap.xml")
    body = response.get_data(as_text=True)

    assert response.status_code == 200
    assert response.mimetype in {"application/xml", "text/xml"}
    assert "<loc>https://swiftpropdf.com/</loc>" in body
    assert "<loc>https://swiftpropdf.com/compress</loc>" in body
