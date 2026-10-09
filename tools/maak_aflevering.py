#!/usr/bin/env python3
"""Maakt een Signaal-aflevering van een script-bestand.

Gebruik:
    python3 tools/maak_aflevering.py scripts/2026-10-10.json           # ElevenLabs + publiceren
    python3 tools/maak_aflevering.py scripts/2026-10-10.json --lokaal  # test met Mac-stem, niets publiceren

Script-formaat (JSON):
    {
      "date": "2026-10-10",
      "title": "Korte titel van de dag",
      "intro": "Goedemorgen, het is vrijdag 10 oktober...",
      "segments": [{"headline": "Kop zoals in de app", "text": "Gesproken tekst..."}],
      "outro": "Dat was Signaal..."
    }

Leest ELEVENLABS_API_KEY en (optioneel) ELEVENLABS_VOICE_ID uit het bestand .env in de projectmap.
"""
import json, os, subprocess, sys, tempfile, urllib.request, urllib.error

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
EP_DIR = os.path.join(ROOT, "episodes")
INDEX = os.path.join(EP_DIR, "episodes.json")
MODEL = "eleven_v4"
DEFAULT_VOICE = "JBFqnCBsd6RMkjVDRZzb"  # "George": warm, rustig, zakelijk; vervang via .env
BITRATE = 128_000
KEEP = 30  # zoveel afleveringen bewaren; oudere audio wordt opgeruimd


def load_env():
    env = {}
    path = os.path.join(ROOT, ".env")
    if os.path.exists(path):
        for line in open(path, encoding="utf-8"):
            line = line.strip()
            if line and not line.startswith("#") and "=" in line:
                k, v = line.split("=", 1)
                env[k.strip()] = v.strip().strip('"').strip("'")
    return env


def build_text(script):
    """Plakt intro, items en outro aan elkaar en berekent waar elke kop begint (0..1)."""
    parts = [script["intro"].strip()]
    starts = []
    for seg in script["segments"]:
        starts.append(len("\n\n".join(parts)) + 2)
        parts.append(seg["text"].strip())
    parts.append(script["outro"].strip())
    text = "\n\n".join(parts)
    headlines = [{"text": s["headline"], "at": round(pos / len(text), 4)}
                 for s, pos in zip(script["segments"], starts)]
    return text, headlines


def tts_elevenlabs(text, out_path, env):
    key = env.get("ELEVENLABS_API_KEY") or os.environ.get("ELEVENLABS_API_KEY")
    if not key:
        sys.exit("FOUT: geen ELEVENLABS_API_KEY gevonden in .env")
    voice = env.get("ELEVENLABS_VOICE_ID") or DEFAULT_VOICE
    url = f"https://api.elevenlabs.io/v1/text-to-speech/{voice}?output_format=mp3_44100_128"
    body = {"text": text, "model_id": MODEL, "language_code": "nl",
            "voice_settings": {"stability": 0.5, "similarity_boost": 0.8}}

    def call(payload):
        req = urllib.request.Request(url, data=json.dumps(payload).encode(), method="POST",
                                     headers={"xi-api-key": key, "Content-Type": "application/json",
                                              "Accept": "audio/mpeg"})
        with urllib.request.urlopen(req, timeout=300) as r:
            return r.read()

    try:
        audio = call(body)
    except urllib.error.HTTPError as e:
        if e.code in (400, 422):  # model accepteert bepaalde instellingen niet: probeer kaal
            print(f"Let op: ElevenLabs gaf {e.code} ({e.read()[:300]!r}), opnieuw zonder extra instellingen")
            audio = call({"text": text, "model_id": MODEL})
        else:
            sys.exit(f"FOUT van ElevenLabs ({e.code}): {e.read()[:500]!r}")
    with open(out_path, "wb") as f:
        f.write(audio)
    return len(audio) * 8 / BITRATE


def tts_lokaal(text, out_path):
    """Testmodus: Nederlandse Mac-stem, uitvoer als .m4a."""
    with tempfile.TemporaryDirectory() as tmp:
        aiff = os.path.join(tmp, "a.aiff")
        subprocess.run(["say", "-v", "Xander", "-o", aiff, text], check=True)
        subprocess.run(["afconvert", "-f", "m4af", "-d", "aac", aiff, out_path], check=True)
    info = subprocess.run(["afinfo", out_path], capture_output=True, text=True).stdout
    for line in info.splitlines():
        if "estimated duration" in line:
            return float(line.split(":")[1].split()[0])
    return 0


def git(*args):
    return subprocess.run(["git", "-C", ROOT, *args], capture_output=True, text=True)


def main():
    if len(sys.argv) < 2:
        sys.exit(__doc__)
    lokaal = "--lokaal" in sys.argv
    script = json.load(open(sys.argv[1], encoding="utf-8"))
    date = script["date"]
    text, headlines = build_text(script)
    print(f"Script {date}: {len(text)} tekens, {len(text.split())} woorden, {len(headlines)} items")
    if len(text) > 9500:
        sys.exit("FOUT: tekst is te lang voor één ElevenLabs-verzoek (max ~9.500 tekens). Maak hem korter.")

    ext = "m4a" if lokaal else "mp3"
    name = f"{date}.{ext}"
    out = os.path.join(EP_DIR, name)
    duration = tts_lokaal(text, out) if lokaal else tts_elevenlabs(text, out, load_env())
    print(f"Audio klaar: episodes/{name} ({duration / 60:.1f} min)")

    index = json.load(open(INDEX, encoding="utf-8"))
    eps = [e for e in index.get("episodes", []) if e["date"] != date]
    eps.append({"date": date, "title": script["title"], "audio": f"episodes/{name}",
                "duration": round(duration, 1), "headlines": headlines})
    eps.sort(key=lambda e: e["date"], reverse=True)
    for old in eps[KEEP:]:
        p = os.path.join(ROOT, old["audio"])
        if os.path.exists(p):
            os.remove(p)
    index["episodes"] = eps[:KEEP]
    with open(INDEX, "w", encoding="utf-8") as f:
        json.dump(index, f, ensure_ascii=False, indent=2)

    if lokaal:
        print("Testmodus: niet gepubliceerd.")
        return
    git("add", "-A", "episodes", "scripts")
    c = git("commit", "-m", f"Aflevering {date}: {script['title']}")
    print(c.stdout.strip() or c.stderr.strip())
    if git("remote").stdout.strip():
        p = git("push", "-q", "origin", "main")
        print("Gepubliceerd." if p.returncode == 0 else f"FOUT bij publiceren: {p.stderr.strip()}")
    else:
        print("Nog geen online opslag gekoppeld: alleen lokaal opgeslagen.")


if __name__ == "__main__":
    main()
