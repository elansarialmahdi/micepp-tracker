from app.services.detectors import (
    fingerprint_web_technologies,
    parse_nmap_detections,
    parse_whatweb_detections,
    referenced_web_assets,
)


def test_nmap_product_and_version_are_separate_fields() -> None:
    payload = b"""<?xml version="1.0"?>
    <nmaprun><host><ports>
      <port protocol="tcp" portid="21"><state state="open"/>
        <service name="ftp" product="Pure-FTPd" method="probed"/></port>
      <port protocol="tcp" portid="53"><state state="open"/>
        <service name="domain" product="PowerDNS Authoritative Server" version="4.9.16"/></port>
      <port protocol="tcp" portid="80"><state state="open"/>
        <service name="http" product="LiteSpeed httpd"/></port>
      <port protocol="tcp" portid="465"><state state="open"/>
        <service name="smtp" product="Exim smtpd" version="4.99.4"/></port>
    </ports></host></nmaprun>"""

    detections = parse_nmap_detections(payload)
    by_port = {item.port: item for item in detections}

    assert (by_port[21].name, by_port[21].version) == ("Pure-FTPd", None)
    assert (by_port[53].name, by_port[53].version) == (
        "PowerDNS Authoritative Server",
        "4.9.16",
    )
    assert (by_port[80].name, by_port[80].version) == ("LiteSpeed", None)
    assert (by_port[465].name, by_port[465].version) == ("Exim", "4.99.4")


def test_web_fingerprints_html_assets_meta_cdn_and_http3() -> None:
    html = """
      <html><head>
        <meta property="og:title" content="Exemple">
        <link rel="stylesheet" href="https://fonts.bunny.net/css?family=inter">
        <link rel="preconnect" href="https://assets.example.b-cdn.net">
        <script src="https://cdn.jsdelivr.net/npm/alpinejs@3.14.9/dist/cdn.min.js"></script>
        <script src="https://unpkg.com/axios@1.7.9/dist/axios.min.js"></script>
        <script src="https://cdn.jsdelivr.net/npm/swiper@11.1.1/swiper-bundle.min.js"></script>
        <script src="https://cdn.tailwindcss.com/3.4.1"></script>
      </head><body x-data="{}"></body></html>
    """

    detections = fingerprint_web_technologies({"alt-svc": 'h3=":443"; ma=86400'}, html, port=443)
    by_name = {item.name: item for item in detections}

    assert by_name["Alpine.js"].version == "3.14.9"
    assert by_name["Axios"].version == "1.7.9"
    assert by_name["Swiper"].version == "11.1.1"
    assert "Tailwind CSS" in by_name
    assert {"Bunny Fonts", "Bunny CDN", "Unpkg", "Open Graph", "HTTP/3"} <= set(by_name)
    assert all(item.port == 443 for item in detections)


def test_web_fingerprints_compiled_javascript_and_css() -> None:
    html = """
      <script src="/build/assets/app.js"></script>
      <link rel="stylesheet" href="/build/assets/app.css">
    """
    assets = {
        "https://example.test/build/assets/app.js": (
            'var runtime={version:"3.14.9",flushAndStopDeferringMutations:stop};'
            "const client=axios.create({});"
        ),
        "https://example.test/build/assets/app.css": ":root{--tw-ring-color:#fff}",
    }

    detections = fingerprint_web_technologies({}, html, port=443, assets=assets)
    by_name = {item.name: item for item in detections}

    assert by_name["Alpine.js"].version == "3.14.9"
    assert "Axios" in by_name
    assert "Tailwind CSS" in by_name
    assert referenced_web_assets(html, "https://example.test/") == list(assets)


def test_whatweb_json_keeps_technologies_versions_and_certainty() -> None:
    payload = b"""[{
      "target": "https://example.test/",
      "http_status": 200,
      "plugins": {
        "LiteSpeed": {},
        "Open-Graph-Protocol": {"version": ["website"]},
        "WordPress": {"version": ["6.8.1"], "certainty": 80},
        "PHP": {"version": ["8.3.20", "8.3"], "certainty": 100},
        "Title": {"string": ["Example"]},
        "IP": {"string": ["203.0.113.10"]},
        "Cookies": {"string": ["session"]}
      }
    }]"""

    detections = parse_whatweb_detections(payload, port=443)
    by_name = {item.name: item for item in detections}

    assert set(by_name) == {"LiteSpeed", "Open Graph", "WordPress", "PHP"}
    assert by_name["Open Graph"].version is None
    assert by_name["WordPress"].version == "6.8.1"
    assert by_name["WordPress"].confidence == 0.8
    assert by_name["PHP"].version == "8.3.20"
    assert by_name["PHP"].evidence["all_versions"] == ["8.3.20", "8.3"]
    assert all(item.source == "whatweb" and item.port == 443 for item in detections)
