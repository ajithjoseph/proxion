from proxion import roblox


def test_cert_install_and_uninstall(tmp_path, monkeypatch):
    monkeypatch.setenv("PROXION_HOME", str(tmp_path / "home"))
    monkeypatch.setenv("LOCALAPPDATA", str(tmp_path / "la"))
    v = tmp_path / "la" / "Roblox" / "Versions" / "version-abc"
    (v / "ssl").mkdir(parents=True)
    (v / "RobloxPlayerBeta.exe").write_bytes(b"")
    (v / "ssl" / "cacert.pem").write_text("ORIGINAL\n")

    assert roblox.install_cert() == [v / "ssl" / "cacert.pem"]
    text = (v / "ssl" / "cacert.pem").read_text()
    assert text.startswith("ORIGINAL") and "BEGIN CERTIFICATE" in text
    assert roblox.install_cert() == []  # idempotent

    roblox.uninstall_cert()
    assert (v / "ssl" / "cacert.pem").read_text().strip() == "ORIGINAL"
