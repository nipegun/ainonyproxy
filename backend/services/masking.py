#!/usr/bin/env -S PYTHONDONTWRITEBYTECODE=1 python3

from dataclasses import dataclass, field
from typing import Optional

from config import MaskingConfig
from services.pii_detector import PiiEntity


@dataclass
class MaskingContext:
  mapping: dict[str, str] = field(default_factory=dict)
  reverse_mapping: dict[str, str] = field(default_factory=dict)
  counters: dict[str, int] = field(default_factory=dict)


@dataclass
class MaskingResult:
  masked: str
  context: MaskingContext


cMarkerFormat = "<{TYPE}_{N}>"


def fCreateMaskingContext() -> MaskingContext:
  """Creates a new masking context for a request"""
  return MaskingContext()


def _fGenerateMarker(pEntityType: str, pContext: MaskingContext) -> str:
  """Generates a marker for a PII entity type"""
  vCounter = pContext.counters.get(pEntityType, 0) + 1
  pContext.counters[pEntityType] = vCounter
  return cMarkerFormat.replace("{TYPE}", pEntityType).replace("{N}", str(vCounter))


def fMask(
  pText: str,
  pEntities: list[PiiEntity],
  pContext: Optional[MaskingContext] = None
) -> MaskingResult:
  """
  Masks the PII entities of the text, replacing them with markers.

  First it assigns markers in order of appearance (ascending start position),
  then it replaces from the end to the start to keep the indexes right.
  """
  vContext = pContext or fCreateMaskingContext()

  if len(pEntities) == 0:
    return MaskingResult(masked=pText, context=vContext)

  try:
    # First pass: sort by ascending start to assign in order
    aSortedByStart = sorted(pEntities, key=lambda pEntity: pEntity.start)

    # Assign markers in order of appearance
    dEntityMarkers: dict[int, str] = {}
    for vEntity in aSortedByStart:
      vOriginalValue = pText[vEntity.start:vEntity.end]

      # Check whether there is already a marker for this exact value
      vMarker = vContext.reverse_mapping.get(vOriginalValue)

      if not vMarker:
        vMarker = _fGenerateMarker(vEntity.entity_type, vContext)
        vContext.mapping[vMarker] = vOriginalValue
        vContext.reverse_mapping[vOriginalValue] = vMarker

      dEntityMarkers[id(vEntity)] = vMarker

    # Second pass: sort by descending start to replace
    aSortedByEnd = sorted(pEntities, key=lambda pEntity: pEntity.start, reverse=True)

    vResult = pText
    for vEntity in aSortedByEnd:
      vMarker = dEntityMarkers[id(vEntity)]
      vResult = vResult[:vEntity.start] + vMarker + vResult[vEntity.end:]

    return MaskingResult(masked=vResult, context=vContext)
  except Exception as vError:
    print(f"Error masking the text: {vError}")
    raise


def fUnmaskText(
  pText: str,
  pContext: MaskingContext,
  pConfig: MaskingConfig
) -> str:
  """Unmasks a text replacing the markers with the original values"""
  vResult = pText

  try:
    # Sort by descending length to avoid partial replacements
    aMarkers = sorted(pContext.mapping.keys(), key=len, reverse=True)

    for vMarker in aMarkers:
      vOriginalValue = pContext.mapping[vMarker]
      vReplacement = f"{pConfig.marker_text}{vOriginalValue}" if pConfig.show_markers else vOriginalValue
      vResult = vResult.replace(vMarker, vReplacement)

    return vResult
  except Exception as vError:
    print(f"Error unmasking the text: {vError}")
    raise


def fMaskMessages(
  pMessages: list[dict],
  pEntitiesPerMessage: list[list[PiiEntity]]
) -> tuple[list[dict], MaskingContext]:
  """Masks several messages (for chat completions)"""
  vContext = fCreateMaskingContext()

  aMasked = []
  for vIndex, vMessage in enumerate(pMessages):
    aEntities = pEntitiesPerMessage[vIndex] if vIndex < len(pEntitiesPerMessage) else []
    vResult = fMask(vMessage.get("content", ""), aEntities, vContext)
    aMasked.append({**vMessage, "content": vResult.masked})

  return aMasked, vContext


def fUnmaskStreamFragment(
  pBuffer: str,
  pNewFragment: str,
  pContext: MaskingContext,
  pConfig: MaskingConfig
) -> tuple[str, str]:
  """
  Streaming helper: processes fragments and unmasks once markers are complete.

  Returns (output, remaining_buffer).
  """
  vCombined = pBuffer + pNewFragment

  # Look for the last position that is safe to unmask
  vMarkerStart = vCombined.rfind("<")

  if vMarkerStart == -1:
    # No potential marker, safe to process everything
    return fUnmaskText(vCombined, pContext, pConfig), ""

  # Check whether there is a complete marker after the last "<"
  vAfterStart = vCombined[vMarkerStart:]
  vHasCompleteMarker = ">" in vAfterStart

  if vHasCompleteMarker:
    # The marker is complete, everything can be processed
    return fUnmaskText(vCombined, pContext, pConfig), ""

  # Partial marker detected, it is kept in the buffer
  vSafeToProcess = vCombined[:vMarkerStart]
  vToBuffer = vCombined[vMarkerStart:]

  return fUnmaskText(vSafeToProcess, pContext, pConfig), vToBuffer


def fFlushStreamBuffer(
  pBuffer: str,
  pContext: MaskingContext,
  pConfig: MaskingConfig
) -> str:
  """Flushes the remaining buffer at the end of the stream"""
  if not pBuffer:
    return ""
  return fUnmaskText(pBuffer, pContext, pConfig)


def fUnmaskResponse(
  pResponse: dict,
  pContext: MaskingContext,
  pConfig: MaskingConfig
) -> dict:
  """Unmasks a chat response replacing the markers in every choice"""
  vResponseCopy = pResponse.copy()
  aChoices = []

  try:
    for vChoice in pResponse.get("choices", []):
      vChoiceCopy = vChoice.copy()
      dMessage = vChoice.get("message", {}).copy()
      vContent = dMessage.get("content", "")
      dMessage["content"] = fUnmaskText(vContent, pContext, pConfig)
      vChoiceCopy["message"] = dMessage
      aChoices.append(vChoiceCopy)
  except Exception as vError:
    print(f"Error unmasking the response: {vError}")
    raise

  vResponseCopy["choices"] = aChoices
  return vResponseCopy
