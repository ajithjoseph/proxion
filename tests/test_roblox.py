from proxion import roblox


def test_cert_install_and_uninstall(tmp_path, monkeypatch):
    monkeypatch.setenv("PROXION_HOME", str(tmp_path / "home"))
    monkeypatch.setenv("LOCALAPPDATA", str(tmp_path / "la"))
    v = tmp_path / "la" / "Roblox" / "Versions" / "version-abc"
    (v / "ssl").mkdir(parents=True)
    (v / "RobloxPlayerBeta.exe").write_bytes(b"")
    (v / "ssl" / "cacert.pem").write_text("ORIGINAL\n")

    assert roblox.install_cert() == ([v / "ssl" / "cacert.pem"], [])
    text = (v / "ssl" / "cacert.pem").read_text()
    assert text.startswith("ORIGINAL") and "BEGIN CERTIFICATE" in text
    assert roblox.install_cert() == ([], [])  # idempotent

    roblox.uninstall_cert()
    assert (v / "ssl" / "cacert.pem").read_text().strip() == "ORIGINAL"


def test_cert_bundle_bytes_kept_and_unmatched_marker(tmp_path, monkeypatch):
    monkeypatch.setenv("LOCALAPPDATA", str(tmp_path / "la"))
    v = tmp_path / "la" / "Roblox" / "Versions" / "version-abc"
    (v / "ssl").mkdir(parents=True)
    (v / "RobloxPlayerBeta.exe").write_bytes(b"")
    original = "# Zertifikat \u00e9\n-----BEGIN CERTIFICATE-----\nREAL\n-----END CERTIFICATE-----\n".encode("latin-1")
    (v / "ssl" / "cacert.pem").write_bytes(original)
    roblox.install_cert()
    roblox.uninstall_cert()
    assert (v / "ssl" / "cacert.pem").read_bytes() == original  # non-ASCII bytes survive

    # A cut off Proxion block must not take the real CAs after it with it
    broken = roblox.MARKER + "\n-----BEGIN CERTIFICATE-----\nOURS\n-----END CERTIFICATE-----\nREAL CA\n"
    assert "REAL CA" in roblox._strip_block(broken)
    assert "OURS" not in roblox._strip_block(broken)
