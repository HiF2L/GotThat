import logging
import asyncio
import re
import aiohttp
from typing import Optional, Dict, Any, List

logger = logging.getLogger(__name__)

STOP_WORDS = {
    "и", "в", "во", "на", "с", "со", "к", "ко", "по", "о", "об", "обо", "про", "для", "от", "до", "из",
    "что", "как", "почему", "зачем", "где", "когда", "который", "какой", "это", "этот", "эта", "эти",
    "архитектура", "концепция", "основы", "введение", "принцип", "принципы", "устройство", "структура",
    "работа", "механизм", "механизмы", "теория", "практика", "система", "системы", "обзор", "урок",
    "великий", "привратник", "сознания", "velikiy", "privratnik", "soznaniya",
    "architecture", "concept", "concepts", "basics", "introduction", "principle", "principles",
    "how", "what", "why", "overview", "theory", "practice", "system", "systems", "guide", "tutorial",
    "the", "a", "an", "and", "or", "in", "on", "at", "to", "for", "with", "by", "about", "from", "of"
}

GENERIC_CROSS_DOMAIN_MODIFIERS = {
    "first", "second", "third", "fourth", "law", "laws", "principle", "principles",
    "theory", "theories", "model", "models", "effect", "effects", "system", "systems",
    "method", "methods", "process", "rule", "rules", "index", "scale", "analysis",
    "concept", "concepts", "overview", "introduction", "basics", "science", "studies",
    "general", "classic", "standard", "diagram", "image", "photo", "picture", "figure",
    "ergonomics", "ergonomic",
    "закон", "законы", "принцип", "принципы", "теория", "теории", "модель", "модели",
    "эффект", "эффекты", "система", "системы", "метод", "методы", "правило", "правила",
    "эргономика", "эргономики"
}

NEGATIVE_IMAGE_TERMS = {
    "jar", "specimen", "formalin", "troglodytes", "museum", "preserved", "cadaver",
    "autopsy", "skull", "dissection", "dead", "fossil", "flask", "d.669", "taxidermy",
    "pathology", "organ in jar", "jar of", "amphibian", "invertebrate"
}

GENERIC_BROAD_TERMS = {
    "brain", "human", "science", "computer", "system", "program", "biology", "physics"
}

TECH_LOGOS = {
    "n8n": {"url": "https://raw.githubusercontent.com/n8n-io/n8n/master/assets/n8n-logo.png", "caption": "n8n — Workflow Automation Platform"},
    "fastapi": {"url": "https://fastapi.tiangolo.com/img/logo-margin/logo-teal.png", "caption": "FastAPI Framework"},
    "docker": {"url": "https://upload.wikimedia.org/wikipedia/commons/thumb/4/4e/Docker_%28container_engine%29_logo.svg/1024px-Docker_%28container_engine%29_logo.svg.png", "caption": "Docker Container Engine"},
    "kubernetes": {"url": "https://upload.wikimedia.org/wikipedia/commons/thumb/3/39/Kubernetes_logo_without_workmark.svg/1024px-Kubernetes_logo_without_workmark.svg.png", "caption": "Kubernetes Orchestration"},
    "react": {"url": "https://upload.wikimedia.org/wikipedia/commons/thumb/a/a7/React-icon.svg/1024px-React-icon.svg.png", "caption": "React UI Library"},
    "python": {"url": "https://upload.wikimedia.org/wikipedia/commons/thumb/c/c3/Python-logo-notext.svg/1024px-Python-logo-notext.svg.png", "caption": "Python Programming Language"},
    "postgresql": {"url": "https://upload.wikimedia.org/wikipedia/commons/thumb/2/29/Postgresql_elephant.svg/1024px-Postgresql_elephant.svg.png", "caption": "PostgreSQL Database"},
    "redis": {"url": "https://upload.wikimedia.org/wikipedia/commons/thumb/6/6b/Redis_Logo.svg/1024px-Redis_Logo.svg.png", "caption": "Redis In-Memory Data Store"},
    "git": {"url": "https://upload.wikimedia.org/wikipedia/commons/thumb/e/e0/Git-logo.svg/1024px-Git-logo.svg.png", "caption": "Git Distributed Version Control"},
    "linux": {"url": "https://upload.wikimedia.org/wikipedia/commons/thumb/3/35/Tux.svg/800px-Tux.svg.png", "caption": "Linux Kernel & OS"},
}


class ImageFinderService:
    """
    Fast subagent that finds verified, high-resolution, open-license educational
    and historical photos/diagrams from Wikipedia, Wikimedia Commons, and verified tech repositories.
    If no authentic real-world media exists, returns None to allow the high-density SVG visualizer to render.
    """

    USER_AGENT = "GotItLearningPlatform/1.0 (educational-ai-assistant; contact@gotit.local)"

    def extract_core_entities(self, query: str, concept_title: str) -> List[str]:
        combined = f"{query} {concept_title}".lower()
        tokens = re.findall(r'[a-zA-Zа-яА-ЯёЁ0-9\-\+]+', combined)
        filtered = [t for t in tokens if len(t) > 1 and t not in STOP_WORDS and t not in GENERIC_BROAD_TERMS]
        entities = [t for t in filtered if t not in GENERIC_CROSS_DOMAIN_MODIFIERS and len(t) > 2]
        return entities if entities else filtered

    async def find_educational_image(
        self,
        query: str,
        concept_title: str = "",
    ) -> Optional[Dict[str, str]]:
        if not query or len(query.strip()) < 2:
            query = concept_title

        clean_query = query.strip()
        core_entities = self.extract_core_entities(clean_query, concept_title)

        # 1. Check curated high-res tech logos for software tools
        if core_entities:
            for ent in core_entities:
                if ent in TECH_LOGOS:
                    return TECH_LOGOS[ent]

        # 2. Search Wikipedia with strict core entity relevance & negative filtering
        if core_entities:
            try:
                wiki_img = await self._search_wikipedia(clean_query, core_entities, concept_title)
                if wiki_img:
                    return wiki_img
            except Exception as e:
                logger.debug(f"Wikipedia image search failed for '{clean_query}': {e}")

        # 3. Search Wikimedia Commons with strict core entity relevance & negative filtering
        if core_entities:
            try:
                commons_img = await self._search_wikimedia_commons(clean_query, core_entities, concept_title)
                if commons_img:
                    return commons_img
            except Exception as e:
                logger.debug(f"Wikimedia commons search failed for '{clean_query}': {e}")

        return None

    async def _search_wikipedia(self, query: str, core_entities: List[str], concept_title: str) -> Optional[Dict[str, str]]:
        url = "https://en.wikipedia.org/w/api.php"
        params = {
            "action": "query",
            "generator": "search",
            "gsrsearch": query,
            "gsrlimit": 6,
            "prop": "pageimages|pageterms",
            "piprop": "original|thumbnail",
            "pithumbsize": 960,
            "format": "json",
            "origin": "*",
        }
        headers = {"User-Agent": self.USER_AGENT}

        async with aiohttp.ClientSession(timeout=aiohttp.ClientTimeout(total=3.0)) as session:
            async with session.get(url, params=params, headers=headers) as resp:
                if resp.status != 200:
                    return None
                data = await resp.json()
                pages = data.get("query", {}).get("pages", {})
                for pid, p in pages.items():
                    title = p.get("title", "")
                    terms = " ".join(p.get("terms", {}).get("description", []))
                    orig = p.get("thumbnail", {}) or p.get("original", {})
                    src = orig.get("source", "")
                    combined_check = f"{title} {terms} {src}".lower()

                    if any(neg in combined_check for neg in NEGATIVE_IMAGE_TERMS):
                        continue

                    if not any(e in combined_check for e in core_entities):
                        continue

                    if src and not src.endswith(".svg") and not src.endswith(".ogg") and not src.endswith(".pdf"):
                        clean_caption = f"{title} — схема/иллюстрация" if "anatomy" in combined_check or "diagram" in combined_check else title
                        return {"url": src, "caption": clean_caption}
        return None

    async def _search_wikimedia_commons(self, query: str, core_entities: List[str], concept_title: str) -> Optional[Dict[str, str]]:
        url = "https://commons.wikimedia.org/w/api.php"
        params = {
            "action": "query",
            "generator": "search",
            "gsrsearch": f"file:{query}",
            "gsrnamespace": "6",
            "gsrlimit": 6,
            "prop": "imageinfo",
            "iiprop": "url|size|mime",
            "iiurlwidth": 960,
            "format": "json",
            "origin": "*",
        }
        headers = {"User-Agent": self.USER_AGENT}

        async with aiohttp.ClientSession(timeout=aiohttp.ClientTimeout(total=3.0)) as session:
            async with session.get(url, params=params, headers=headers) as resp:
                if resp.status != 200:
                    return None
                data = await resp.json()
                pages = data.get("query", {}).get("pages", {})
                for pid, p in pages.items():
                    title = p.get("title", "")
                    combined_check = f"{title}".lower()

                    if any(neg in combined_check for neg in NEGATIVE_IMAGE_TERMS):
                        continue

                    if not any(e in combined_check for e in core_entities):
                        continue

                    info = p.get("imageinfo", [])
                    if info:
                        img = info[0]
                        u = img.get("thumburl") or img.get("url")
                        mime = img.get("mime", "")
                        if u and mime.startswith("image/") and not u.endswith(".svg") and not u.endswith(".ogg") and not u.endswith(".pdf"):
                            clean_caption = title.replace("File:", "").replace(".jpg", "").replace(".png", "")
                            return {"url": u, "caption": clean_caption}
        return None


image_finder = ImageFinderService()
