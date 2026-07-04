"""
Image classification service. This is the ONLY file that talks to Gemini
for classification. Everything else calls `classify_image()` and doesn't
care whether it's mock or real.

MOCK MODE (default, no API key set):
  Returns a plausible-looking classification so the rest of the pipeline
  (severity scoring, clustering, dashboard) works end-to-end today.

REAL MODE (GEMINI_API_KEY set in .env):
  Calls the actual Gemini API. No other file needs to change.

To get a key: aistudio.google.com -> sign in -> "Get API key" -> paste
into .env as GEMINI_API_KEY=your_key_here -> restart the app.
"""
import base64
import hashlib
import json
import logging
from dataclasses import dataclass

from app.core.config import settings
from app.models.report import IssueCategory

logger = logging.getLogger(__name__)


@dataclass
class ClassificationResult:
    category: IssueCategory
    confidence: float
    raw_response: str  # stored on the report for debugging during the hackathon


# Deterministic mock categories, so the same test photo always classifies
# the same way during development (makes debugging saner than random).
_MOCK_CATEGORIES = list(IssueCategory)


def _mock_classify(image_bytes: bytes) -> ClassificationResult:
    # Hash the image bytes to deterministically pick a category + confidence.
    # This is NOT real classification — it's a stand-in so your team can
    # build and demo the full pipeline before a Gemini key is ready.
    digest = hashlib.sha256(image_bytes).hexdigest()
    category_index = int(digest[:8], 16) % len(_MOCK_CATEGORIES)
    confidence = 0.65 + (int(digest[8:10], 16) % 30) / 100  # 0.65 - 0.94

    category = _MOCK_CATEGORIES[category_index]
    raw = json.dumps({
        "mode": "MOCK",
        "note": "Set GEMINI_API_KEY in .env for real classification.",
        "category": category.value,
        "confidence": round(confidence, 2),
    })
    logger.info("MOCK classification: %s (%.2f confidence)", category.value, confidence)
    return ClassificationResult(category=category, confidence=round(confidence, 2), raw_response=raw)


def _real_classify(image_bytes: bytes) -> ClassificationResult:
    """
    Real Gemini call. Only executes when GEMINI_API_KEY is set.
    Uses the google-genai SDK.
    """
    from google import genai  # imported here so mock mode never requires the package

    client = genai.Client(api_key=settings.GEMINI_API_KEY)

    prompt = (
        "You are classifying a citizen-submitted photo of a possible urban "
        "pollution issue for a municipal reporting system. Respond ONLY with "
        "JSON, no markdown fences, no preamble, in exactly this shape:\n"
        '{"category": "<one of: garbage, water_pollution, air_pollution, '
        'industrial_waste, sewage, other>", "confidence": <float 0.0-1.0>, '
        '"evidence": "<one short sentence on what you see that supports this>"}'
    )

    response = client.models.generate_content(
        model=settings.GEMINI_MODEL,
        contents=[
            {"inline_data": {"mime_type": "image/jpeg", "data": base64.b64encode(image_bytes).decode()}},
            prompt,
        ],
    )

    text = response.text.strip()
    # Defensive: strip markdown fences if the model adds them despite instructions.
    text = text.replace("```json", "").replace("```", "").strip()

    try:
        parsed = json.loads(text)
        category = IssueCategory(parsed["category"])
        confidence = float(parsed["confidence"])
    except (json.JSONDecodeError, KeyError, ValueError) as e:
        logger.warning("Gemini response didn't match expected shape: %s | raw: %s", e, text)
        category = IssueCategory.other
        confidence = 0.3

    return ClassificationResult(category=category, confidence=confidence, raw_response=text)


def classify_image(image_bytes: bytes) -> ClassificationResult:
    """
    Single entry point used by routers/services. Switches mock/real based
    on whether GEMINI_API_KEY is set — no caller needs to know which mode
    is active.
    """
    if settings.GEMINI_MOCK_MODE:
        return _mock_classify(image_bytes)
    return _real_classify(image_bytes)
