"""
Before/after verification service — the differentiator feature from the
roadmap. Compares an original report photo against a follow-up "after"
photo and decides whether the issue looks resolved.

Same mock/real pattern as classifier.py: works today without a key,
swaps to real Gemini calls the moment GEMINI_API_KEY is set.
"""
import base64
import hashlib
import json
import logging

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
        explanation=f"MOCK MODE: simulated comparison result. Set GEMINI_API_KEY in .env "
                    f"for a real before/after visual comparison.",
    )


def _real_verify(before_bytes: bytes, after_bytes: bytes) -> VerificationResult:
    from google import genai

    client = genai.Client(api_key=settings.GEMINI_API_KEY)

    prompt = (
        "You are comparing two photos for a municipal pollution reporting system: "
        "a 'before' photo showing a reported issue, and an 'after' photo submitted "
        "later claiming the issue is resolved. Respond ONLY with JSON, no markdown "
        "fences, in exactly this shape:\n"
        '{"verified": <true or false>, "confidence": <float 0.0-1.0>, '
        '"explanation": "<one short sentence on what changed or did not change>"}'
    )

    response = client.models.generate_content(
        model=settings.GEMINI_MODEL,
        contents=[
            {"inline_data": {"mime_type": "image/jpeg", "data": base64.b64encode(before_bytes).decode()}},
            {"inline_data": {"mime_type": "image/jpeg", "data": base64.b64encode(after_bytes).decode()}},
            prompt,
        ],
    )

    text = response.text.strip().replace("```json", "").replace("```", "").strip()

    try:
        parsed = json.loads(text)
        verified = bool(parsed["verified"])
        confidence = float(parsed["confidence"])
        explanation = str(parsed["explanation"])
    except (json.JSONDecodeError, KeyError, ValueError) as e:
        logger.warning("Gemini verification response malformed: %s | raw: %s", e, text)
        verified, confidence, explanation = False, 0.3, "Could not parse model response; treated as unverified."

    status = VerificationStatus.verified if verified else VerificationStatus.not_verified
    return VerificationResult(verification_status=status, confidence=confidence, explanation=explanation)


def verify_before_after(before_bytes: bytes, after_bytes: bytes) -> VerificationResult:
    if settings.GEMINI_MOCK_MODE:
        return _mock_verify(before_bytes, after_bytes)
    return _real_verify(before_bytes, after_bytes)