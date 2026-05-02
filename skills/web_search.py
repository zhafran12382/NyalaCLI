from __future__ import annotations

import os
from typing import Any

import requests

from core.permissions import redact_secrets

from .base import SkillResult, truncate


class WebSearchSkill:
    name = "web_search"
    description = "Cari web via Tavily jika TAVILY_API_KEY tersedia."
    parameters_schema = {"query": "Query pencarian.", "max_results": "Jumlah hasil, default 5."}

    def run(self, args: dict[str, Any], context: dict[str, Any]) -> SkillResult:
        api_key = os.environ.get("TAVILY_API_KEY", "")
        if not api_key:
            return SkillResult(False, "TAVILY_API_KEY belum ada. Jalankan setup dan isi Tavily API key opsional.")
        query = str(args.get("query", "")).strip()
        if not query:
            return SkillResult(False, "Query kosong.")
        max_results = max(1, min(int(args.get("max_results") or 5), 10))
        payload = {"api_key": api_key, "query": query, "search_depth": "basic", "max_results": max_results}
        try:
            response = requests.post("https://api.tavily.com/search", json=payload, timeout=45)
        except requests.RequestException as exc:
            return SkillResult(False, f"Gagal Tavily search: {exc}")
        if response.status_code >= 400:
            return SkillResult(False, f"Tavily HTTP {response.status_code}: {redact_secrets(response.text[:300])}")
        try:
            data = response.json()
        except ValueError:
            return SkillResult(False, "Respons Tavily bukan JSON valid.")
        lines = [f"Query: {query}"]
        for item in data.get("results", [])[:max_results]:
            title = item.get("title", "(tanpa judul)")
            url = item.get("url", "")
            content = item.get("content", "")
            lines.append(f"- {title}\n  {url}\n  {content[:500]}")
        output, truncated = truncate("\n".join(lines), 6000)
        return SkillResult(True, output, "\n".join(lines) if truncated else None)
