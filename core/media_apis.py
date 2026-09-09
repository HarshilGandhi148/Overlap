"""Backend-only provider clients. Explicit imports, bounded retries, safe errors."""
from datetime import datetime, timezone
import json
import os
import re
import time
import requests
from core.contracts import CategorySearchError


def stamp():
    return datetime.now(timezone.utc).isoformat()


def request_json(method, url, **kwargs):
    for attempt in range(3):
        try:
            response = requests.request(method, url, timeout=15, **kwargs)
            if response.status_code == 429 or response.status_code >= 500:
                if attempt < 2:
                    try:
                        delay = min(float(response.headers.get("Retry-After", 2 ** attempt)), 5)
                    except ValueError:
                        delay = 2 ** attempt
                    time.sleep(max(0, delay))
                    continue
            if response.status_code in (401, 403):
                raise AuthenticationError("Provider authentication failed. Check the backend credentials.")
            response.raise_for_status()
            return response.json()
        except AuthenticationError:
            raise
        except (requests.RequestException, ValueError) as exc:
            if attempt == 2:
                raise CategorySearchError("Provider request failed or was rate limited. Retry later; imported records are retained.") from None
    raise CategorySearchError("Provider request failed.")


class AuthenticationError(CategorySearchError):
    pass


def normalize_movie(raw):
    if raw.get("Response") == "False":
        raise CategorySearchError("OMDb could not find this movie or rejected the request. Check the title, key, and quota.")
    if not raw.get("imdbID") or not raw.get("Title") or raw.get("Type", "movie") != "movie":
        raise CategorySearchError("OMDb returned an invalid movie record.")
    tags = [] if raw.get("Genre") in (None, "N/A") else [v.strip().replace("Sci-Fi", "Sci-fi") for v in raw["Genre"].split(",")]
    record = {"id": raw["imdbID"], "provider_id": raw["imdbID"], "title": raw["Title"],
              "description": "" if raw.get("Plot") in (None, "N/A") else raw["Plot"],
              "tags": tags, "genres_known": bool(tags), "source": "OMDb", "imported_at": stamp(),
              "source_url": f"https://www.imdb.com/title/{raw['imdbID']}/"}
    runtime = re.fullmatch(r"(\d+) min", raw.get("Runtime", ""))
    if runtime:
        record["duration"] = int(runtime.group(1))
    if str(raw.get("Year", "")).isdigit():
        record["year"] = int(raw["Year"])
    if raw.get("Rated") not in (None, "N/A"):
        record["certificate"] = raw["Rated"]
    if str(raw.get("Poster", "")).startswith("https://"):
        record["image_url"] = raw["Poster"]
    return record


class OMDb:
    def __init__(self):
        self.key = os.getenv("OMDB_API_KEY", "")
        if not self.key:
            raise CategorySearchError("Set OMDB_API_KEY in the backend .env before importing movies.")

    def lookup(self, title_or_id):
        field = "i" if re.fullmatch(r"tt\d+", title_or_id) else "t"
        return normalize_movie(request_json("GET", "https://www.omdbapi.com/", params={
            "apikey": self.key, field: title_or_id, "type": "movie", "plot": "full"}))

    def search(self, title, page=1):
        raw = request_json("GET", "https://www.omdbapi.com/", params={
            "apikey": self.key, "s": title, "type": "movie", "page": page})
        if raw.get("Response") == "False":
            if raw.get("Error") == "Movie not found!":
                return []
            raise CategorySearchError("OMDb search failed. Check credentials and quota.")
        return raw.get("Search", [])


def normalize_game(raw):
    if not raw.get("id") or not raw.get("name"):
        raise CategorySearchError("IGDB returned an invalid game record.")
    configs = []
    for row in raw.get("multiplayer_modes", []):
        platform = row.get("platform")
        if not isinstance(platform, dict) or not platform.get("name"):
            continue  # An unassociated capacity cannot prove platform-specific support.
        for mode, maximum, coop in [("Local", "offlinemax", "offlinecoopmax"), ("Online", "onlinemax", "onlinecoopmax")]:
            if row.get(maximum, 0) > 0:
                configs.append({"platform": platform["name"], "mode": mode,
                                "max_players": row[maximum], "coop_max": row.get(coop), "source": "IGDB"})
            elif row.get(coop, 0) > 0:
                configs.append({"platform": platform["name"], "mode": mode,
                                "max_players": row[coop], "coop_max": row[coop], "source": "IGDB"})
    tags = [v["name"] for v in raw.get("genres", [])]
    if any(c.get("coop_max", 0) and c["coop_max"] > 1 for c in configs):
        tags.append("Cooperative")
    record = {"id": f"igdb-{raw['id']}", "provider_id": str(raw["id"]), "title": raw["name"],
              "description": raw.get("summary", ""), "tags": tags, "genres_known": bool(raw.get("genres")),
              "platforms": [p["name"] for p in raw.get("platforms", [])], "multiplayer": configs,
              "format": "Video", "source": "IGDB", "source_url": raw.get("url"), "imported_at": stamp()}
    cover = raw.get("cover", {}).get("url", "")
    if cover.startswith("//"):
        cover = "https:" + cover
    if cover.startswith("https://"):
        record["image_url"] = cover.replace("t_thumb", "t_cover_big")
    return record


class IGDB:
    fields = ("name,summary,url,genres.name,platforms.name,cover.url,"
              "multiplayer_modes.platform.name,multiplayer_modes.offlinemax,"
              "multiplayer_modes.onlinemax,multiplayer_modes.offlinecoopmax,multiplayer_modes.onlinecoopmax")

    def __init__(self):
        self.client_id = os.getenv("IGDB_CLIENT_ID", "")
        self.secret = os.getenv("IGDB_CLIENT_SECRET", "")
        self.token, self.expires, self.last_request = "", 0, 0
        if not self.client_id or not self.secret:
            raise CategorySearchError("Set IGDB_CLIENT_ID and IGDB_CLIENT_SECRET in backend .env before importing games.")

    def authenticate(self):
        if time.monotonic() >= self.expires:
            raw = request_json("POST", "https://id.twitch.tv/oauth2/token", data={
                "client_id": self.client_id, "client_secret": self.secret, "grant_type": "client_credentials"})
            if not raw.get("access_token"):
                raise AuthenticationError("Twitch did not issue a token. Check the IGDB credentials.")
            self.token = raw["access_token"]
            self.expires = time.monotonic() + max(0, int(raw.get("expires_in", 3600)) - 60)

    def query(self, clause):
        for attempt in range(2):
            self.authenticate()
            time.sleep(max(0, .26 - (time.monotonic() - self.last_request)))
            self.last_request = time.monotonic()
            try:
                raw = request_json("POST", "https://api.igdb.com/v4/games", headers={
                    "Client-ID": self.client_id, "Authorization": f"Bearer {self.token}"},
                    data=f"fields {self.fields}; {clause}")
                if not isinstance(raw, list):
                    raise CategorySearchError("IGDB returned an unexpected response.")
                return [normalize_game(game) for game in raw]
            except AuthenticationError:
                self.expires = 0
                if attempt:
                    raise

    def import_multiplayer(self, count=100):
        return self.query(f"where multiplayer_modes != null; sort id asc; limit {min(max(int(count), 1), 500)};")

    def search(self, title):
        return self.query(f"search {json.dumps(title)}; limit 10;")
