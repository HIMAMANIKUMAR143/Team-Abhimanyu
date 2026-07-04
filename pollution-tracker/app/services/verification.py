import hashlib
import json
import logging

from pydantic import BaseModel
from google import genai
from google.genai import types

from app.core.config import settings
from app.models.report import VerificationStatus
from app.schemas.report import VerificationResult

logger = logging.getLogger(__name__)


def _mock_verify(before_bytes: bytes, after_bytes: bytes) -> VerificationResult:
    # Deterministic mock: if the two images are byte-identical, call it
    # "not verified" (nothing changed). Otherwise derive a pseudo-random
    # but stable confidence from the combined hash.
    if before_bytes == after_bytes:
        return VerificationResult(
            verification_status=VerificationStatus.not_verified,
            confidence=0.20,
            explanation="MOCK MODE: before/after photos are identical, so no change was detected. "
                        "Set GEMINI_API_KEY in .env for real comparison.",
        )

    digest = hashlib.sha256(before_bytes + after_bytes).hexdigest()
    confidence = 0.55 + (int(digest[:4], 16) % 40) / 100  # 0.55 - 0.94
    status = VerificationStatus.verified if confidence > 0.7 else VerificationStatus.not_verified

    return VerificationResult(
        verification_status=status,
        confidence=round(confidence, 2),
        explanation="MOCK MODE: simulated comparison result. Set GEMINI_API_KEY in .env "
                    "for a real before/after visual comparison.",
    )


class GeminiVerificationSchema(BaseModel):
    """Pydantic schema to strictly enforce Gemini's JSON output structure."""
    verified: bool
    confidence: float
    explanation: str


def _real_verify(before_bytes: bytes, after_bytes: bytes) -> VerificationResult:
    """
    Real Gemini call. Only executes when GEMINI_API_KEY is set.
    Uses the google-genai SDK with Structured Outputs to guarantee valid JSON.
    """
    client = genai.Client(api_key=settings.GEMINI_API_KEY)

    prompt = (
        "You are comparing two photos for a municipal pollution reporting system. "
        "The first image is the 'before' photo showing a reported issue. "
        "The second image is the 'after' photo submitted later claiming the issue is resolved. "
        "Analyze both images and determine if the issue has been visibly resolved."
    )

    try:
        response = client.models.generate_content(
            model=settings.GEMINI_MODEL,
            contents=[
                prompt,
                "Image 1 (Before):",
                types.Part.from_bytes(data=before_bytes, mime_type="image/jpeg"),
                "Image 2 (After):",
                types.Part.from_bytes(data=after_bytes, mime_type="image/jpeg"),
            ],
            config=types.GenerateContentConfig(
                response_mime_type="application/json",
                response_schema=GeminiVerificationSchema,
                temperature=0.1,  # Low temperature for highly deterministic analysis
            )
        )

        # Because we used response_schema, response.text is guaranteed to be 
        # a valid JSON string matching GeminiVerificationSchema.
        parsed = json.loads(response.text)
        verified = bool(parsed["verified"])
        confidence = float(parsed["confidence"])
        explanation = str(parsed["explanation"])

    except Exception as e:
        logger.exception("Gemini verification failed or returned invalid format")
        # Fallback in case of network failure or API error
        verified = False
        confidence = 0.3
        explanation = f"Could not parse model response or API failed: {str(e)}"

    status = VerificationStatus.verified if verified else VerificationStatus.not_verified
    
    return VerificationResult(
        verification_status=status, 
        confidence=confidence, 
        explanation=explanation
    )


def verify_before_after(before_bytes: bytes, after_bytes: bytes) -> VerificationResult:
    """
    Single entry point used by the verification router. Switches mock/real based
    on whether GEMINI_MOCK_MODE is true.
    """
    if settings.GEMINI_MOCK_MODE:
        return _mock_verify(before_bytes, after_bytes)
    return _real_verify(before_bytes, after_bytes)
