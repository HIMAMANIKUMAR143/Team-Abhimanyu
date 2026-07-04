import hashlib
import json
import logging
from dataclasses import dataclass

from pydantic import BaseModel
from google import genai
from google.genai import types

from app.core.config import settings
from app.models.report import IssueCategory

logger = logging.getLogger(__name__)


@dataclass
class ClassificationResult:
    category: IssueCategory
    confidence: float
    raw_response: str  # stored on the report for debugging during development


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
    return ClassificationResult(
        category=category, 
        confidence=round(confidence, 2), 
        raw_response=raw
    )


class GeminiClassificationSchema(BaseModel):
    """Pydantic schema to strictly enforce Gemini's JSON output structure."""
    category: IssueCategory
    confidence: float
    evidence: str


def _real_classify(image_bytes: bytes) -> ClassificationResult:
    """
    Real Gemini call. Only executes when GEMINI_API_KEY is set.
    Uses the google-genai SDK with Structured Outputs to guarantee valid JSON.
    """
    client = genai.Client(api_key=settings.GEMINI_API_KEY)

    prompt = (
        "You are classifying a citizen-submitted photo of a possible urban "
        "pollution issue for a municipal reporting system. Analyze the image "
        "and categorize the issue based on the provided schema."
    )

    try:
        # Generate content using Structured Outputs
        response = client.models.generate_content(
            model=settings.GEMINI_MODEL,
            contents=[
                types.Part.from_bytes(data=image_bytes, mime_type="image/jpeg"),
                prompt,
            ],
            config=types.GenerateContentConfig(
                response_mime_type="application/json",
                response_schema=GeminiClassificationSchema,
                temperature=0.1,  # Low temperature for more deterministic classification
            )
        )

        # Because we used response_schema, response.text is guaranteed to be 
        # a valid JSON string matching GeminiClassificationSchema.
        parsed = json.loads(response.text)
        category = IssueCategory(parsed["category"])
        confidence = float(parsed["confidence"])
        
    except Exception as e:
        logger.exception("Gemini classification failed or returned invalid format")
        # Fallback in case of network failure or severe API error
        return ClassificationResult(
            category=IssueCategory.other,
            confidence=0.3,
            raw_response=f'{{"error": "{str(e)}" }}'
        )

    return ClassificationResult(
        category=category, 
        confidence=confidence, 
        raw_response=response.text
    )


def classify_image(image_bytes: bytes) -> ClassificationResult:
    """
    Single entry point used by routers/services. Switches mock/real based
    on whether GEMINI_MOCK_MODE is true — no caller needs to know which mode
    is active.
    """
    if settings.GEMINI_MOCK_MODE:
        return _mock_classify(image_bytes)
    return _real_classify(image_bytes)
