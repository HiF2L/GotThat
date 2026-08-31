import re
import uuid

CYRILLIC_TO_LATIN = {
    'а': 'a', 'б': 'b', 'в': 'v', 'г': 'g', 'д': 'd', 'е': 'e', 'ё': 'e',
    'ж': 'zh', 'з': 'z', 'и': 'i', 'й': 'y', 'к': 'k', 'л': 'l', 'м': 'm',
    'н': 'n', 'о': 'o', 'п': 'p', 'р': 'r', 'с': 's', 'т': 't', 'у': 'u',
    'ф': 'f', 'х': 'kh', 'ц': 'ts', 'ч': 'ch', 'ш': 'sh', 'щ': 'shch',
    'ъ': '', 'ы': 'y', 'ь': '', 'э': 'e', 'ю': 'yu', 'я': 'ya',
}


def generate_slug(text: str, max_length: int = 64) -> str:
    """
    Converts any title (Russian, English, symbols) into a clean, human-readable URL slug.
    e.g. "Архитектура и концепция n8n" -> "arkhitektura-i-kontseptsiya-n8n"
    """
    if not text:
        return f"item-{uuid.uuid4().hex[:6]}"

    t = text.lower().strip()
    res = []
    for char in t:
        if char in CYRILLIC_TO_LATIN:
            res.append(CYRILLIC_TO_LATIN[char])
        else:
            res.append(char)
    latin_text = "".join(res)

    slug = re.sub(r'[^a-z0-9]+', '-', latin_text).strip('-')
    slug = re.sub(r'-+', '-', slug)

    if not slug:
        slug = f"item-{uuid.uuid4().hex[:6]}"

    if len(slug) > max_length:
        slug = slug[:max_length].rstrip('-')

    return slug
