#!/usr/bin/env -S PYTHONDONTWRITEBYTECODE=1 python3

import json
import time
from typing import Optional

from fastapi import APIRouter, Request, HTTPException, Path
from fastapi.responses import JSONResponse, StreamingResponse
from pydantic import BaseModel, ConfigDict, field_validator

from config import MaskingConfig, fGetConfig
from services.dates import fNowStorage
from services.decision import fGetRouter, MaskDecision
from services.logger import fLogRequest, RequestLogData
from services.masking import (
  fUnmaskResponse,
  fUnmaskStreamFragment,
  fFlushStreamBuffer,
  MaskingContext
)

vChatRouter = APIRouter(tags=["ai"])


class ChatMessageSchema(BaseModel):
  role: str
  content: str

  @field_validator("role")
  @classmethod
  def mValidateRole(cls, pValue):
    if pValue not in ("system", "user", "assistant"):
      raise ValueError("role must be 'system', 'user' or 'assistant'")
    return pValue


class ChatRequestSchema(BaseModel):
  model_config = ConfigDict(extra="allow")

  messages: list[ChatMessageSchema]
  model: Optional[str] = None
  stream: Optional[bool] = False

  @field_validator("messages")
  @classmethod
  def mValidateMessages(cls, pValue):
    if len(pValue) < 1:
      raise ValueError("At least one message is required")
    return pValue


def fFormatMessagesForLog(pMessages: list[dict]) -> str:
  return "\n".join(f"[{vMessage['role']}] {vMessage['content']}" for vMessage in pMessages)


def fCreateLogData(
  pDecision: MaskDecision,
  pModel: str,
  pProvider: str,
  pStart: float,
  pResponse: Optional[dict] = None,
  pOriginalContent: Optional[str] = None,
  pMaskedContent: Optional[str] = None,
  pProviderResponse: Optional[str] = None,
  pClientResponse: Optional[str] = None
) -> RequestLogData:
  # Only what the configuration allows is written to the database:
  #   log_content        -> the real (unmasked) texts: original request and answer to the client
  #   log_masked_content -> the masked texts: masked request and answer of the provider
  vLoggingConfig = fGetConfig().logging
  if not vLoggingConfig.log_content:
    pOriginalContent = None
    pClientResponse = None
  if not vLoggingConfig.log_masked_content:
    pMaskedContent = None
    pProviderResponse = None

  return RequestLogData(
    timestamp=fNowStorage(),
    mode=pDecision.mode,
    provider=pProvider,
    model=pModel,
    pii_detected=pDecision.pii_result.has_pii,
    entities=list(set(vEntity.entity_type for vEntity in pDecision.pii_result.new_entities)),
    latency_ms=int((time.time() - pStart) * 1000),
    scan_time_ms=pDecision.pii_result.scan_time_ms,
    prompt_tokens=pResponse.get("usage", {}).get("prompt_tokens") if pResponse else None,
    completion_tokens=pResponse.get("usage", {}).get("completion_tokens") if pResponse else None,
    language=pDecision.pii_result.language,
    language_fallback=pDecision.pii_result.language_fallback,
    detected_language=pDecision.pii_result.detected_language,
    original_content=pOriginalContent,
    masked_content=pMaskedContent,
    provider_response=pProviderResponse,
    client_response=pClientResponse
  )


@vChatRouter.get("/", summary="List the available AI APIs")
async def fListProviders(pRequest: Request):
  """Lists every available API with its full URL"""
  vRouter = fGetRouter()
  dProvidersInfo = vRouter.mGetProvidersInfo()

  # Build the base URL of the server
  vHost = pRequest.headers.get("host", "localhost:11443")
  vScheme = pRequest.headers.get("x-forwarded-proto", pRequest.url.scheme)
  vBaseUrl = f"{vScheme}://{vHost}"

  # Build the list of available APIs
  dApis = {}
  for vName, dInfo in dProvidersInfo["providers"].items():
    dApis[vName] = {
      "url": f"{vBaseUrl}/api/ai/{vName}",
      "type": dInfo.get("format", ""),
      "method": "POST",
      "content_type": "application/json"
    }

  return {
    "message": "ainonyproxy - LLM proxy with privacy protection",
    "available_apis": dApis
  }


@vChatRouter.post("/{pProvider}", summary="Chat completion through a provider (OpenAI compatible)")
async def fChatCompletions(
  pRequest: Request,
  pProvider: str = Path(..., description="Name of the LLM provider")
):
  """
  Chat completions endpoint for a specific provider.
  Compatible with the OpenAI API.
  """
  vStart = time.time()
  vRouter = fGetRouter()

  # Validate that the provider exists
  if not vRouter.mProviderExists(pProvider):
    aAvailable = vRouter.mListProviders()
    raise HTTPException(status_code=404, detail={
      "error": {
        "message": f"Provider '{pProvider}' not found",
        "type": "not_found",
        "available_providers": aAvailable
      }
    })

  try:
    dBody = await pRequest.json()
    vChatRequest = ChatRequestSchema(**dBody)
  except Exception as vError:
    raise HTTPException(status_code=400, detail={
      "error": {
        "message": "Invalid request body",
        "type": "invalid_request_error",
        "details": str(vError)
      }
    })

  try:
    aMessages = [{"role": vMessage.role, "content": vMessage.content} for vMessage in vChatRequest.messages]
    vDecision = await vRouter.mDecide(aMessages, pProvider)
  except Exception as vError:
    print(f"[PII ERROR] {type(vError).__name__}: {vError}")
    raise HTTPException(status_code=503, detail={
      "error": {
        "message": f"PII detection service not available: {vError}",
        "type": "service_unavailable"
      }
    })

  vClient = vRouter.mGetClient(pProvider)
  vMaskingConfig = vRouter.mGetMaskingConfig()

  # Prepare the request and the content for logging
  dRequest = dBody.copy()
  vOriginalContent = fFormatMessagesForLog(aMessages)
  vMaskedContent = None

  if vDecision.pii_result.has_pii:
    dRequest["messages"] = vDecision.masked_messages
    vMaskedContent = fFormatMessagesForLog(vDecision.masked_messages)

  try:
    vResult = await vClient.mCompleteChat(dRequest)

    # Response headers
    dHeaders = {
      "X-Ainonyproxy-Mode": vDecision.mode,
      "X-Ainonyproxy-Provider": pProvider,
      "X-Ainonyproxy-PII-Detected": str(vDecision.pii_result.has_pii).lower(),
      "X-Ainonyproxy-Language": vDecision.pii_result.language
    }

    if vDecision.pii_result.language_fallback:
      dHeaders["X-Ainonyproxy-Language-Fallback"] = "true"

    dHeaders["X-Ainonyproxy-PII-Masked"] = str(vDecision.pii_result.has_pii).lower()

    vUserAgent = pRequest.headers.get("User-Agent")

    if vResult.is_streaming:
      # With streaming the full response cannot be captured
      fLogRequest(
        fCreateLogData(vDecision, vResult.model, pProvider, vStart, None, vOriginalContent, vMaskedContent, None, None),
        vUserAgent
      )

      if vDecision.pii_result.has_pii:
        return StreamingResponse(
          fCreateUnmaskedStream(
            vResult.response,
            vDecision.masking_context,
            vMaskingConfig
          ),
          media_type="text/event-stream",
          headers=dHeaders
        )
      else:
        return StreamingResponse(
          vResult.response,
          media_type="text/event-stream",
          headers=dHeaders
        )

    # JSON response
    dResponse = vResult.response

    # Capture the response of the provider (with masked data when it applies)
    vProviderResponse = dResponse.get("choices", [{}])[0].get("message", {}).get("content", "")

    # Unmask when there is PII
    if vDecision.pii_result.has_pii:
      dResponse = fUnmaskResponse(
        dResponse,
        vDecision.masking_context,
        vMaskingConfig
      )

    # Capture the final response sent to the client (unmasked)
    vClientResponse = dResponse.get("choices", [{}])[0].get("message", {}).get("content", "")

    fLogRequest(
      fCreateLogData(vDecision, vResult.model, pProvider, vStart, dResponse, vOriginalContent, vMaskedContent, vProviderResponse, vClientResponse),
      vUserAgent
    )

    return JSONResponse(content=dResponse, headers=dHeaders)

  except Exception as vError:
    vMessage = str(vError)
    raise HTTPException(status_code=502, detail={
      "error": {
        "message": f"LLM provider error: {vMessage}",
        "type": "provider_error"
      }
    })


async def fCreateUnmaskedStream(
  pSource,
  pContext: MaskingContext,
  pConfig: MaskingConfig
):
  """Creates a generator that unmasks SSE content"""
  vContentBuffer = ""

  async for vChunk in pSource:
    try:
      vFragment = vChunk.decode("utf-8")
    except UnicodeDecodeError:
      continue
    aLines = vFragment.split("\n")

    for vLine in aLines:
      if vLine.startswith("data: "):
        vData = vLine[6:]

        if vData == "[DONE]":
          yield b"data: [DONE]\n\n"
          continue

        try:
          dParsed = json.loads(vData)
          vContent = dParsed.get("choices", [{}])[0].get("delta", {}).get("content", "")

          if vContent:
            vOutput, vContentBuffer = fUnmaskStreamFragment(
              vContentBuffer,
              vContent,
              pContext,
              pConfig
            )

            if vOutput:
              dParsed["choices"][0]["delta"]["content"] = vOutput
              yield f"data: {json.dumps(dParsed)}\n\n".encode()
          else:
            yield f"data: {vData}\n\n".encode()
        except json.JSONDecodeError:
          yield f"{vLine}\n".encode()
      elif vLine.strip():
        yield f"{vLine}\n".encode()

  # Flush the remaining buffer
  if vContentBuffer:
    vFlushed = fFlushStreamBuffer(vContentBuffer, pContext, pConfig)
    if vFlushed:
      dFinalEvent = {
        "id": f"flush-{int(time.time() * 1000)}",
        "object": "chat.completion.chunk",
        "created": int(time.time()),
        "choices": [{
          "index": 0,
          "delta": {"content": vFlushed},
          "finish_reason": None
        }]
      }
      yield f"data: {json.dumps(dFinalEvent)}\n\n".encode()
