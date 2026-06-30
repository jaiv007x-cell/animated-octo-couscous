
from pathlib import Path
import yaml

ALLOWED_DOMAIN_HINTS = (
    ".gov.in", ".nic.in", "gov.in", "gujarat.gov.in", "maharashtra.gov.in",
    "karnataka.gov.in", "telangana.gov.in", "sikkim.gov.in", "py.gov.in",
    "apegazette.cgg.gov.in", "apcfss.in", "aptonline.in", "haryanatax.gov.in",
    "hptax.gov.in", "jk.gov.in", "jkexcise.nic.in", "rajasthan.gov.in",
    "rajexcise.gov.in", "excise.wb.gov.in", "eabgari.tripura.gov.in",
    "exciseportal.py.gov.in", "excise.cg.nic.in", "ddnexcise.gov.in",
    "etdut.gov.in", "legislative.gov.in", "indiacode.nic.in", "meghalaya.gov.in",
    "excise.meghalaya.gov.in", "upsdc.gov.in",
)

def test_verified_registry_has_no_starter_or_fake_notes():
    cfg = yaml.safe_load(Path("data/sources.yaml").read_text(encoding="utf-8"))
    assert cfg["registry_version"] == "v6.2_verified_original_sources"
    assert len(cfg["states"]) == 36
    total = 0
    for state in cfg["states"]:
        assert state["sources"], state["code"]
        for src in state["sources"]:
            total += 1
            blob = " ".join(str(src.get(k, "")) for k in ("name", "url", "notes")).lower()
            assert "starter url" not in blob
            assert "verify production" not in blob
            assert "abkaritoday" not in blob
            assert src.get("verification_status") == "VERIFIED_OFFICIAL_OR_GOVT_HOSTED"
    assert total >= 100

def test_verified_registry_domains_are_official_or_govt_hosted():
    cfg = yaml.safe_load(Path("data/sources.yaml").read_text(encoding="utf-8"))
    bad=[]
    for state in cfg["states"]:
        for src in state["sources"]:
            url=src["url"].lower()
            if not any(hint in url for hint in ALLOWED_DOMAIN_HINTS):
                bad.append((state["code"], url))
    assert not bad
