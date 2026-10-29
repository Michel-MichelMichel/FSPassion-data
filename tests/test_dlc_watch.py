"""Essais de tools/dlc_watch.py, sans Internet (extrait réel de dlc.php)."""

from __future__ import annotations

import datetime as dt
import importlib.util
import io
import json
import shutil
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
spec = importlib.util.spec_from_file_location("dlc_watch", ROOT / "tools" / "dlc_watch.py")
dw = importlib.util.module_from_spec(spec)
spec.loader.exec_module(dw)

PAGE = """
<div class="column">
    <div class="dlc" style="">
        <a href="dlc-detail.php?dlc_id=fs25beansandalpacas" class="dlc__title clearfix">
            <h4 class="float-left">Beans &amp; Alpacas Expansion</h4>
            <div class="dlc__price float-right">$29.99 </div>
        </a>
        <div class="dlc__content">
            <a href="dlc-detail.php?dlc_id=fs25beansandalpacas"><img class="dlc__img" src="/img/content/products/fs25/fs25beansandalpacas-cover.jpg?v=1986796121" alt=""></a>
        </div>
    </div></div>
<div class="column">
    <div class="dlc" style="">
        <a href="dlc-detail.php?dlc_id=fs25newcoolpack" class="dlc__title clearfix">
            <h4 class="float-left">Cool Tractors &amp; GÖWEIL Pack</h4>
            <div class="dlc__price float-right">$9.99 </div>
        </a>
        <div class="dlc__content">
            <a href="dlc-detail.php?dlc_id=fs25newcoolpack"><img class="dlc__img" src="/img/content/products/fs25/fs25newcoolpack-cover.jpg?v=1" alt=""></a>
        </div>
    </div></div>
<div class="column">
    <div class="dlc" style="">
        <a href="https://gdn.giants-software.com/videoTutorials2.php" class="dlc__title clearfix">
            <h4 class="float-left">Modding Tutorials 6.0</h4>
            <div class="dlc__price float-right">FREE</div>
        </a>
        <div class="dlc__content"><a href="#"><img class="dlc__img" src="/img/content/products/fs25/fs25mt60-cover.jpg?v=4" alt=""></a></div>
    </div></div>
"""


@pytest.fixture()
def repo(tmp_path, monkeypatch):
    dlc = tmp_path / "dlc"
    shutil.copytree(ROOT / "dlc", dlc)
    monkeypatch.setattr(dw, "DLC_DIR", dlc)
    monkeypatch.setattr(dw, "CATALOG", dlc / "dlc_catalog.json")
    monkeypatch.setattr(dw, "SEEN", dlc / "giants_seen.json")
    from PIL import Image

    def fake_fetch(url, limit=0):
        buf = io.BytesIO()
        Image.new("RGB", (600, 600), "green").save(buf, "JPEG")
        return buf.getvalue()

    monkeypatch.setattr(dw, "fetch", fake_fetch)
    return dlc


def test_parse_list_reads_name_image_and_skips_non_dlc():
    rows = dw.parse_list(PAGE)
    assert [r["id"] for r in rows] == ["fs25beansandalpacas", "fs25newcoolpack"]
    assert rows[0]["name"] == "Beans & Alpacas Expansion" and rows[0]["game"] == "FS25"
    assert rows[0]["image"] == "https://www.farming-simulator.com/img/content/products/fs25/fs25beansandalpacas-cover.jpg"


def test_keywords_follow_the_catalog_convention():
    assert dw.keywords("Beans & Alpacas Expansion") == ["beans", "alpacas"]
    assert dw.keywords("Cool Tractors & GÖWEIL Pack") == ["cool", "tractors", "goweil"]


def test_new_dlc_is_added_with_icon_and_known_one_is_skipped(repo):
    lines = dw.run(PAGE, dt.date(2026, 11, 3), use_steam=False)
    assert len(lines) == 1 and "Cool Tractors" in lines[0]
    cat = json.loads((repo / "dlc_catalog.json").read_text(encoding="utf-8"))
    e = cat["versions"]["FS25"]["dlc"][-1]
    assert e["name"] == "Cool Tractors & GÖWEIL Pack" and e["file"] is None
    assert e["keywords"] == ["cool", "tractors", "goweil"] and e["status"] == "released"
    assert e["release_date"] == "2026-11-03" and e["icon"] == "newcoolpack.jpg" and len(e["sha256"]) == 64
    from PIL import Image

    assert Image.open(repo / "icons_dlc_fs25" / "newcoolpack.jpg").size == (512, 512)
    assert "fs25newcoolpack" in json.loads((repo / "giants_seen.json").read_text())["seen"]
    # Le lendemain : rien de neuf.
    assert dw.run(PAGE, dt.date(2026, 11, 4), use_steam=False) == []


def test_announced_dlc_becomes_released_on_its_date(repo, monkeypatch):
    monkeypatch.setattr(dw, "steam_release", lambda game, kws: {"steam_id": 1, "name": "x", "coming_soon": True,
                                                                "date": dt.date(2026, 12, 1)})
    dw.run(PAGE, dt.date(2026, 11, 3))
    cat = json.loads((repo / "dlc_catalog.json").read_text(encoding="utf-8"))
    e = cat["versions"]["FS25"]["dlc"][-1]
    assert e["status"] == "announced" and e["release_date"] == "2026-12-01"
    lines = dw.run(PAGE, dt.date(2026, 12, 1))
    assert any("passé en « released »" in x for x in lines)


def test_steam_dates():
    assert dw.parse_steam_date("Oct 28, 2026") == dt.date(2026, 10, 28)
    assert dw.parse_steam_date("28 Oct, 2026") == dt.date(2026, 10, 28)
    assert dw.parse_steam_date("Coming soon") is None


def test_hashes_are_fixed_after_an_image_is_replaced(repo):
    (repo / "icons_dlc_fs25" / "beansAndAlpacas.jpg").write_bytes(b"autre image")
    assert dw.fix_hashes() == ["FS25 Beans & Alpacas Expansion"]
    assert dw.fix_hashes() == []
