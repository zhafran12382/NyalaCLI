from __future__ import annotations

from typing import Any

import requests
from bs4 import BeautifulSoup

from .base import SkillResult, truncate


class WebScraperSkill:
    name = "web_scraper"
    description = "Ambil halaman web sederhana dan ekstrak title, teks, dan links."
    parameters_schema = {"url": "URL http/https.", "max_chars": "Batas output, default 6000."}

    def run(self, args: dict[str, Any], context: dict[str, Any]) -> SkillResult:
        url = str(args.get("url", "")).strip()
        if not url.startswith(("http://", "https://")):
            return SkillResult(False, "URL harus diawali http:// atau https://")
        max_chars = max(1000, min(int(args.get("max_chars") or 6000), 20000))
        try:
            response = requests.get(
                url,
                headers={"User-Agent": "NyalaCLI/0.1"},
                timeout=45,
            )
        except requests.RequestException as exc:
            return SkillResult(False, f"Gagal mengambil URL: {exc}")
        if response.status_code >= 400:
            return SkillResult(False, f"HTTP {response.status_code} saat mengambil URL.")
        soup = BeautifulSoup(response.text, "html.parser")
        for tag in soup(["script", "style", "noscript"]):
            tag.decompose()
        title = soup.title.string.strip() if soup.title and soup.title.string else "(tanpa title)"
        text = "\n".join(line.strip() for line in soup.get_text("\n").splitlines() if line.strip())
        links = []
        for link in soup.find_all("a", href=True)[:25]:
            label = " ".join(link.get_text(" ").split())[:80] or "(link)"
            links.append(f"- {label}: {link['href']}")
        full = f"Title: {title}\nURL: {url}\n\nText:\n{text}\n\nLinks:\n" + "\n".join(links)
        output, truncated = truncate(full, max_chars)
        return SkillResult(True, output, full if truncated else None)
