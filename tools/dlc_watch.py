"""Surveille les nouveaux DLC de Farming Simulator (GitHub Actions, chaque jour).

Source : la page officielle https://www.farming-simulator.com/dlc.php (nom
exact du DLC, image carrée « cover »). Date de sortie : le magasin Steam, quand
il connaît le DLC.

Pour chaque DLC jamais vu (absent de dlc/giants_seen.json) :
- une entrée est ajoutée au catalogue dlc/dlc_catalog.json : nom, mots-clés
  tirés du nom (le nom du fichier n'est pas connu à la sortie), état
  « announced » + date de sortie si Steam l'annonce pour plus tard, sinon
  « released » ;
- son image est téléchargée dans dlc/icons_dlc_fsXX/ et son empreinte calculée.
Un DLC « announced » dont la date est passée devient « released ».

Le script ne publie rien : le workflow ouvre une pull request, que l'auteur
vérifie, corrige au besoin, puis fusionne (« Merge »). GitHub l'en prévient
par e-mail.

Utilisation : python tools/dlc_watch.py [--summary FICHIER] [--html FICHIER]
"""

from __future__ import annotations

import argparse
import datetime as dt
import hashlib
import html
import io
import json
import re
import sys
import time
import unicodedata
import urllib.request
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
DLC_DIR = ROOT / "dlc"
CATALOG = DLC_DIR / "dlc_catalog.json"
SEEN = DLC_DIR / "giants_seen.json"

BASE = "https://www.farming-simulator.com/"
LIST_URL = BASE + "dlc.php?lang=en&country=us"
# Préfixe de l'identifiant GIANTS → version du catalogue.
GAMES = {"fs19": "FS19", "fs22": "FS22", "fs25": "FS25", "fs28": "FS28"}
# Jeux sur Steam (dates de sortie des DLC). FS28 : à ajouter quand il y sera.
STEAM_APPS = {"FS22": 1248130, "FS25": 2300320}
UA = "FSPassion-data DLC watch (+https://github.com/Michel-MichelMichel/FSPassion-data)"
MAX_ICON = 3 * 1024 * 1024
STOP_WORDS = {"pack", "expansion", "dlc", "the", "and", "of", "edition", "free", "bundle", "n", "s", "a"}

BLOCK_RE = re.compile(
    r'<a href="dlc-detail\.php\?dlc_id=([a-z0-9]+)"[^>]*class="dlc__title[^"]*"[^>]*>\s*'
    r'<h4[^>]*>(.*?)</h4>\s*(?:<div class="dlc__price[^"]*">(.*?)</div>)?'
    r'.*?<img class="dlc__img" src="([^"]+)"',
    re.S,
)


# --------------------------------------------------------------------------
# Lecture des pages
# --------------------------------------------------------------------------

def fetch(url: str, limit: int = 5 * 1024 * 1024) -> bytes:
    req = urllib.request.Request(url, headers={"User-Agent": UA, "Accept-Language": "en"})
    for attempt in range(3):
        try:
            with urllib.request.urlopen(req, timeout=30) as r:  # noqa: S310 - adresses fixes en https
                data = r.read(limit + 1)
            if len(data) > limit:
                raise ValueError(f"réponse trop grosse : {url}")
            return data
        except OSError:
            if attempt == 2:
                raise
            time.sleep(5)
    raise RuntimeError("inaccessible")


def parse_list(page: str) -> list[dict[str, str]]:
    """DLC de la page dlc.php : identifiant, nom, prix, image (dans l'ordre)."""
    out: list[dict[str, str]] = []
    seen: set[str] = set()
    for dlc_id, name, price, img in BLOCK_RE.findall(page):
        if dlc_id in seen:
            continue
        seen.add(dlc_id)
        m = re.match(r"(fs\d\d)", dlc_id)
        if not m or m.group(1) not in GAMES:
            continue
        name = re.sub(r"\s+", " ", html.unescape(re.sub(r"<[^>]+>", "", name))).strip()
        price = re.sub(r"\s+", " ", html.unescape(re.sub(r"<[^>]+>", "", price or ""))).strip()
        img_url = urllib.request.urljoin(BASE, html.unescape(img)).split("?")[0]
        out.append({"id": dlc_id, "game": GAMES[m.group(1)], "name": name, "price": price, "image": img_url})
    return out


def keywords(name: str) -> list[str]:
    """Mots du nom qui reconnaîtront le fichier du DLC (casse ignorée)."""
    ascii_name = unicodedata.normalize("NFKD", name).encode("ascii", "ignore").decode().lower()
    words = [w for w in re.findall(r"[a-z0-9]+", ascii_name) if w not in STOP_WORDS and len(w) > 1]
    out: list[str] = []
    for w in words:
        if w not in out:
            out.append(w)
    return out[:4] or [re.sub(r"[^a-z0-9]", "", ascii_name)[:20]]


# --------------------------------------------------------------------------
# Steam : date de sortie
# --------------------------------------------------------------------------

def parse_steam_date(text: str) -> dt.date | None:
    text = (text or "").strip().replace(",", "")
    for fmt in ("%d %b %Y", "%b %d %Y", "%d %B %Y", "%B %d %Y"):
        try:
            return dt.datetime.strptime(text, fmt).date()
        except ValueError:
            pass
    return None


def steam_release(game: str, kws: list[str]) -> dict[str, Any] | None:
    """Date de sortie trouvée sur Steam pour ce DLC (nom qui contient tous les
    mots-clés), ou None."""
    app = STEAM_APPS.get(game)
    if app is None:
        return None
    try:
        info = json.loads(fetch(f"https://store.steampowered.com/api/appdetails?appids={app}&l=english&cc=us"))
        dlc_ids = (info.get(str(app), {}).get("data") or {}).get("dlc") or []
    except (OSError, ValueError) as exc:
        print(f"  Steam inaccessible : {exc}")
        return None
    for sid in sorted(dlc_ids, reverse=True)[:40]:  # les plus récents d'abord
        try:
            d = json.loads(fetch(f"https://store.steampowered.com/api/appdetails?appids={sid}&l=english&cc=us"))
        except (OSError, ValueError):
            continue
        data = (d.get(str(sid)) or {}).get("data") or {}
        words = set(keywords(data.get("name") or ""))
        if kws and set(kws) <= words:
            rel = data.get("release_date") or {}
            return {"steam_id": sid, "name": data.get("name"), "coming_soon": bool(rel.get("coming_soon")),
                    "date": parse_steam_date(rel.get("date") or "")}
        time.sleep(1.5)  # Steam limite le nombre de demandes
    return None


# --------------------------------------------------------------------------
# Image
# --------------------------------------------------------------------------

def save_icon(url: str, folder: Path, stem: str) -> tuple[str, str, str]:
    """Télécharge l'image, la garde carrée de 256 à 512 px (JPEG). Renvoie
    (nom du fichier, empreinte sha256, remarque)."""
    from PIL import Image  # pip install pillow

    raw = fetch(url, MAX_ICON)
    im = Image.open(io.BytesIO(raw))
    im.load()
    w, h = im.size
    note = f"{w} × {h} px"
    if abs(w - h) > max(w, h) * 0.05:
        note += " — PAS CARRÉE : à remplacer"
    if max(w, h) > 512:
        im = im.convert("RGB")
        im.thumbnail((512, 512), Image.Resampling.LANCZOS)
        note += f", réduite à {im.size[0]} × {im.size[1]} px"
    elif max(w, h) < 256:
        note += " — TROP PETITE : à remplacer"
    folder.mkdir(parents=True, exist_ok=True)
    name = f"{stem}.jpg"
    buf = io.BytesIO()
    im.convert("RGB").save(buf, "JPEG", quality=90, optimize=True, progressive=True)
    data = buf.getvalue()
    (folder / name).write_bytes(data)
    return name, hashlib.sha256(data).hexdigest(), note


# --------------------------------------------------------------------------
# Catalogue
# --------------------------------------------------------------------------

def already_listed(vcat: dict[str, Any], kws: list[str]) -> dict[str, Any] | None:
    for e in vcat.get("dlc") or []:
        text = " ".join([e.get("name") or "", e.get("file") or "", *(e.get("keywords") or [])]).lower()
        words = set(keywords(text)) | set(re.findall(r"[a-z0-9]+", text))
        if kws and set(kws) <= words:
            return e
    return None


def run(page: str, today: dt.date, use_steam: bool = True) -> list[str]:
    """Met à jour le catalogue. Renvoie les lignes du résumé (vide : rien de neuf)."""
    catalog = json.loads(CATALOG.read_text(encoding="utf-8-sig"))
    seen_doc = json.loads(SEEN.read_text(encoding="utf-8")) if SEEN.is_file() else {"seen": []}
    seen = set(seen_doc.get("seen") or [])
    lines: list[str] = []

    dlcs = parse_list(page)
    if not dlcs:
        raise SystemExit("Aucun DLC lu sur dlc.php : la page a sans doute changé, le script est à revoir.")

    for d in dlcs:
        if d["id"] in seen:
            continue
        seen.add(d["id"])
        vcat = catalog["versions"].setdefault(d["game"], {"icons_folder": f"icons_dlc_{d['game'].lower()}", "dlc": []})
        kws = keywords(d["name"])
        old = already_listed(vcat, kws)
        if old is not None:
            lines.append(f"- {d['game']} · **{d['name']}** : déjà au catalogue (« {old.get('name')} »), seulement noté comme vu.")
            continue
        entry: dict[str, Any] = {"file": None, "keywords": kws, "name": d["name"], "type": "dlc"}
        status, release = "released", today
        steam = steam_release(d["game"], kws) if use_steam else None
        if steam and steam["date"]:
            release = steam["date"]
        if steam and (steam["coming_soon"] or (steam["date"] and steam["date"] > today)):
            status = "announced"
        entry.update({"status": status, "release_date": release.isoformat(), "verified": True, "source": "giants"})
        stem = re.sub(r"^fs\d\d", "", d["id"]) or d["id"]
        icon_note = "image introuvable — à ajouter à la main"
        try:
            name, sha, icon_note = save_icon(d["image"], DLC_DIR / vcat["icons_folder"], stem)
            entry["icon"], entry["sha256"] = name, sha
        except Exception as exc:  # noqa: BLE001 - le DLC est proposé quand même
            icon_note += f" ({exc})"
        vcat["dlc"].append(entry)
        lines.append(
            f"- {d['game']} · **{d['name']}** ({d['price'] or 'prix inconnu'}) — état « {status} », "
            f"sortie {release.isoformat()}{' (Steam)' if steam and steam['date'] else ' (date du jour : Steam ne la donne pas)'} ; "
            f"mots-clés `{' '.join(kws)}` ; image : {icon_note}. "
            f"[Fiche GIANTS]({BASE}dlc-detail.php?dlc_id={d['id']})"
        )

    # Les DLC annoncés dont la date est passée sont sortis.
    for vid, vcat in catalog["versions"].items():
        for e in vcat.get("dlc") or []:
            rd = e.get("release_date")
            if e.get("status") == "announced" and isinstance(rd, str) and rd <= today.isoformat():
                e["status"] = "released"
                lines.append(f"- {vid} · **{e.get('name')}** : sorti le {rd}, passé en « released ».")

    if lines:
        catalog["updated"] = today.isoformat()
        CATALOG.write_text(json.dumps(catalog, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
        seen_doc["seen"] = sorted(seen)
        SEEN.write_text(json.dumps(seen_doc, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    return lines


def fix_hashes() -> list[str]:
    """Recalcule l'empreinte de chaque icône (après le remplacement d'une image
    dans la pull request). Renvoie les entrées corrigées."""
    catalog = json.loads(CATALOG.read_text(encoding="utf-8-sig"))
    changed: list[str] = []
    for vid, vcat in catalog["versions"].items():
        folder = DLC_DIR / vcat["icons_folder"]
        files = {f.name.lower(): f for f in folder.glob("*") if f.is_file()} if folder.is_dir() else {}
        for e in vcat.get("dlc") or []:
            names = [e["icon"]] if e.get("icon") else ([f"{e['file']}.png", f"{e['file']}.jpg"] if e.get("file") else [])
            found = next((files[n.lower()] for n in names if n.lower() in files), None)
            sha = hashlib.sha256(found.read_bytes()).hexdigest() if found else None
            if sha != e.get("sha256"):
                if sha:
                    e["sha256"] = sha
                else:
                    e.pop("sha256", None)
                changed.append(f"{vid} {e.get('name')}")
    if changed:
        CATALOG.write_text(json.dumps(catalog, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    return changed


def main(argv: list[str] | None = None) -> int:
    p = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument("--summary", help="fichier Markdown du résumé (texte de la pull request)")
    p.add_argument("--html", help="page dlc.php déjà téléchargée (essais)")
    p.add_argument("--no-steam", action="store_true")
    p.add_argument("--hashes", action="store_true", help="recalculer seulement les empreintes des icônes")
    args = p.parse_args(argv)
    if args.hashes:
        changed = fix_hashes()
        print("Empreintes recalculées : " + (", ".join(changed) if changed else "aucune"))
        return 0
    page = Path(args.html).read_text(encoding="utf-8") if args.html else fetch(LIST_URL).decode("utf-8", "replace")
    lines = run(page, dt.date.today(), use_steam=not args.no_steam)
    if not lines:
        print("Rien de neuf.")
        return 0
    body = "\n".join([
        "Changements trouvés par la surveillance quotidienne des DLC :",
        "",
        *lines,
        "",
        "**À faire** : vérifier le nom, les mots-clés et l'image (onglet *Files changed*). Pour corriger, "
        "modifier les fichiers dans cette branche. Puis **Merge pull request** : FS Passion verra le DLC "
        "dans les 24 h. Un DLC « announced » reste caché dans l'application jusqu'à sa date de sortie.",
        "",
        "Pour changer l'image : *Add file → Upload files* dans cette branche, même nom de fichier ; "
        "son empreinte `sha256` est recalculée toute seule.",
    ])
    print(body)
    if args.summary:
        Path(args.summary).write_text(body + "\n", encoding="utf-8")
    return 0


if __name__ == "__main__":
    sys.exit(main())
