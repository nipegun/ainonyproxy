#!/usr/bin/env -S PYTHONDONTWRITEBYTECODE=1 python3

import json
import time
from dataclasses import dataclass
from typing import AsyncIterator, Optional, Union

import httpx

from config import ProviderConfig

cAnthropicVersion = "2023-06-01"
cDefaultAnthropicMaxTokens = 1024


@dataclass
class ChatMessage:
  role: str
  content: str


@dataclass
class LlmStreamingResult:
  is_streaming: bool = True
  response: AsyncIterator[bytes] = None
  model: str = ""
  provider: str = ""


@dataclass
class LlmJsonResult:
  is_streaming: bool = False
  response: dict = None
  model: str = ""
  provider: str = ""


class LlmClient:
  """LLM client for OpenAI compatible and Anthropic APIs."""

  def __init__(
    self,
    pProvider: ProviderConfig,
    pProviderName: str,
    pDefaultModel: Optional[str] = None
  ):
    self._vUrl = pProvider.url
    self._vApiKey = pProvider.api_key
    self._vFormat = pProvider.format
    self._vProviderName = pProviderName
    self._vDefaultModel = pDefaultModel

  def _mBuildOpenAiHeaders(self) -> dict:
    dHeaders = {"Content-Type": "application/json"}
    if self._vApiKey:
      dHeaders["Authorization"] = f"Bearer {self._vApiKey}"
    return dHeaders

  def _mBuildAnthropicHeaders(self) -> dict:
    dHeaders = {
      "Content-Type": "application/json",
      "anthropic-version": cAnthropicVersion
    }
    if self._vApiKey:
      dHeaders["x-api-key"] = self._vApiKey
    return dHeaders

  def _mExtractContentText(self, pContent) -> str:
    if isinstance(pContent, str):
      return pContent
    if isinstance(pContent, list):
      aTexts = []
      for vPart in pContent:
        if isinstance(vPart, str):
          aTexts.append(vPart)
        elif isinstance(vPart, dict):
          if vPart.get("type") == "text" and "text" in vPart:
            aTexts.append(vPart["text"])
      return "".join(aTexts)
    if isinstance(pContent, dict):
      if pContent.get("type") == "text" and "text" in pContent:
        return pContent["text"]
    return ""

  def _mConvertAnthropicMessages(self, pMessages: list[dict]) -> tuple[list[dict], str]:
    aAnthropicMessages = []
    aSystem = []

    for vMessage in pMessages:
      vRole = vMessage.get("role")
      vContent = self._mExtractContentText(vMessage.get("content"))
      if not vContent:
        continue
      if vRole == "system":
        aSystem.append(vContent)
      elif vRole in ("user", "assistant"):
        aAnthropicMessages.append({"role": vRole, "content": vContent})

    vSystem = "\n\n".join(aSystem).strip()
    return aAnthropicMessages, vSystem

  def _mBuildAnthropicBody(self, pRequest: dict, pModel: str, pIsStreaming: bool) -> dict:
    aMessages = pRequest.get("messages", [])
    aAnthropicMessages, vSystem = self._mConvertAnthropicMessages(aMessages)

    if not aAnthropicMessages:
      raise ValueError("Anthropic needs at least one user/assistant message")

    vMaxTokens = pRequest.get("max_tokens")
    if vMaxTokens is None:
      vMaxTokens = pRequest.get("max_completion_tokens")
    if vMaxTokens is None:
      vMaxTokens = cDefaultAnthropicMaxTokens

    dBody = {
      "model": pModel,
      "messages": aAnthropicMessages,
      "max_tokens": vMaxTokens,
      "stream": pIsStreaming
    }

    if vSystem:
      dBody["system"] = vSystem

    if "temperature" in pRequest:
      dBody["temperature"] = pRequest["temperature"]
    if "top_p" in pRequest:
      dBody["top_p"] = pRequest["top_p"]
    if "top_k" in pRequest:
      dBody["top_k"] = pRequest["top_k"]
    if "metadata" in pRequest:
      dBody["metadata"] = pRequest["metadata"]

    if "stop_sequences" in pRequest:
      dBody["stop_sequences"] = pRequest["stop_sequences"]
    elif "stop" in pRequest:
      vStop = pRequest["stop"]
      if isinstance(vStop, list):
        dBody["stop_sequences"] = vStop
      elif isinstance(vStop, str):
        dBody["stop_sequences"] = [vStop]

    return dBody

  def _mMapAnthropicStopReason(self, pStopReason: Optional[str]) -> Optional[str]:
    if not pStopReason:
      return None
    if pStopReason in ("end_turn", "stop_sequence"):
      return "stop"
    if pStopReason == "max_tokens":
      return "length"
    if pStopReason == "tool_use":
      return "tool_calls"
    return "stop"

  def _mFormatAnthropicResponse(self, pResponse: dict, pModel: str) -> dict:
    vText = self._mExtractContentText(pResponse.get("content", []))
    vFinishReason = self._mMapAnthropicStopReason(pResponse.get("stop_reason"))
    dUsage = pResponse.get("usage", {})
    vPromptTokens = dUsage.get("input_tokens")
    vCompletionTokens = dUsage.get("output_tokens")
    vTotalTokens = None

    if vPromptTokens is not None and vCompletionTokens is not None:
      vTotalTokens = vPromptTokens + vCompletionTokens

    return {
      "id": pResponse.get("id", f"chatcmpl-{int(time.time() * 1000)}"),
      "object": "chat.completion",
      "created": int(time.time()),
      "model": pResponse.get("model", pModel),
      "choices": [
        {
          "index": 0,
          "message": {"role": "assistant", "content": vText},
          "finish_reason": vFinishReason
        }
      ],
      "usage": {
        "prompt_tokens": vPromptTokens,
        "completion_tokens": vCompletionTokens,
        "total_tokens": vTotalTokens
      }
    }

  def _mParseSseEvent(self, pRawEvent: str) -> tuple[str, str]:
    vEvent = ""
    aData = []

    for vLine in pRawEvent.split("\n"):
      if vLine.startswith("event:"):
        vEvent = vLine[6:].strip()
      elif vLine.startswith("data:"):
        aData.append(vLine[5:].strip())

    return vEvent, "\n".join(aData)

  async def mCompleteChat(
    self,
    pRequest: dict
  ) -> Union[LlmStreamingResult, LlmJsonResult]:
    """
    Sends a chat completion request

    Args:
      pRequest: Chat completion request
    """
    vModel = self._vDefaultModel or pRequest.get("model")
    vIsStreaming = pRequest.get("stream", False)

    if not vModel:
      raise ValueError("The model is mandatory in the request")

    if self._vFormat == "anthropic":
      dHeaders = self._mBuildAnthropicHeaders()
      dBody = self._mBuildAnthropicBody(pRequest, vModel, vIsStreaming)

      if vIsStreaming:
        return await self._mCompleteChatStreamingAnthropic(dHeaders, dBody, vModel)
      return await self._mCompleteChatJsonAnthropic(dHeaders, dBody, vModel)

    # OpenAI compatible (default format)
    dHeaders = self._mBuildOpenAiHeaders()
    dBody = {**pRequest, "model": vModel, "stream": vIsStreaming}

    # New OpenAI models use max_completion_tokens instead of max_tokens
    if "api.openai.com" in self._vUrl and "max_tokens" in dBody:
      if "max_completion_tokens" not in dBody:
        dBody["max_completion_tokens"] = dBody.pop("max_tokens")
      else:
        dBody.pop("max_tokens")

    if vIsStreaming:
      return await self._mCompleteChatStreaming(dHeaders, dBody, vModel)
    return await self._mCompleteChatJson(dHeaders, dBody, vModel)

  async def _mCompleteChatJson(
    self,
    pHeaders: dict,
    pBody: dict,
    pModel: str
  ) -> LlmJsonResult:
    try:
      async with httpx.AsyncClient(timeout=120.0) as vClient:
        vResponse = await vClient.post(self._vUrl, headers=pHeaders, json=pBody)

        if not vResponse.is_success:
          vErrorText = vResponse.text
          raise Exception(f"LLM API error: {vResponse.status_code} - {vErrorText}")

        try:
          dJson = vResponse.json()
        except json.JSONDecodeError as vError:
          raise Exception(f"Invalid JSON response from the LLM provider: {vError}")

        return LlmJsonResult(
          is_streaming=False,
          response=dJson,
          model=pModel,
          provider=self._vProviderName
        )
    except httpx.TimeoutException as vError:
      raise Exception(f"Timeout contacting the LLM provider: {vError}")
    except httpx.ConnectError as vError:
      raise Exception(f"Connection error with the LLM provider: {vError}")

  async def _mCompleteChatJsonAnthropic(
    self,
    pHeaders: dict,
    pBody: dict,
    pModel: str
  ) -> LlmJsonResult:
    try:
      async with httpx.AsyncClient(timeout=120.0) as vClient:
        vResponse = await vClient.post(self._vUrl, headers=pHeaders, json=pBody)

        if not vResponse.is_success:
          vErrorText = vResponse.text
          raise Exception(f"LLM API error: {vResponse.status_code} - {vErrorText}")

        try:
          dResponse = vResponse.json()
        except json.JSONDecodeError as vError:
          raise Exception(f"Invalid JSON response from Anthropic: {vError}")

        dFormatted = self._mFormatAnthropicResponse(dResponse, pModel)

        return LlmJsonResult(
          is_streaming=False,
          response=dFormatted,
          model=dFormatted.get("model", pModel),
          provider=self._vProviderName
        )
    except httpx.TimeoutException as vError:
      raise Exception(f"Timeout contacting Anthropic: {vError}")
    except httpx.ConnectError as vError:
      raise Exception(f"Connection error with Anthropic: {vError}")

  async def _mCompleteChatStreaming(
    self,
    pHeaders: dict,
    pBody: dict,
    pModel: str
  ) -> LlmStreamingResult:
    vClient = httpx.AsyncClient(timeout=120.0)

    async def fGenerateStream():
      try:
        async with vClient.stream("POST", self._vUrl, headers=pHeaders, json=pBody) as vResponse:
          if not vResponse.is_success:
            vErrorText = await vResponse.aread()
            raise Exception(f"LLM API error: {vResponse.status_code} - {vErrorText.decode()}")

          async for vChunk in vResponse.aiter_bytes():
            yield vChunk
      finally:
        await vClient.aclose()

    return LlmStreamingResult(
      is_streaming=True,
      response=fGenerateStream(),
      model=pModel,
      provider=self._vProviderName
    )

  async def _mCompleteChatStreamingAnthropic(
    self,
    pHeaders: dict,
    pBody: dict,
    pModel: str
  ) -> LlmStreamingResult:
    vClient = httpx.AsyncClient(timeout=120.0)

    async def fGenerateStream():
      vBuffer = ""
      vId = f"chatcmpl-{int(time.time() * 1000)}"
      vCreated = int(time.time())
      vResponseModel = pModel
      vFinishReason = None

      def fCreateChunk(pDelta: dict, pFinish: Optional[str] = None) -> bytes:
        dChunk = {
          "id": vId,
          "object": "chat.completion.chunk",
          "created": vCreated,
          "model": vResponseModel,
          "choices": [
            {
              "index": 0,
              "delta": pDelta,
              "finish_reason": pFinish
            }
          ]
        }
        return f"data: {json.dumps(dChunk)}\n\n".encode()

      try:
        async with vClient.stream("POST", self._vUrl, headers=pHeaders, json=pBody) as vResponse:
          if not vResponse.is_success:
            vErrorText = await vResponse.aread()
            raise Exception(f"LLM API error: {vResponse.status_code} - {vErrorText.decode()}")

          async for vChunk in vResponse.aiter_bytes():
            vBuffer += vChunk.decode("utf-8")
            vBuffer = vBuffer.replace("\r\n", "\n")

            while "\n\n" in vBuffer:
              vRawEvent, vBuffer = vBuffer.split("\n\n", 1)
              vEvent, vData = self._mParseSseEvent(vRawEvent)

              if not vData:
                continue
              if vData == "[DONE]":
                yield b"data: [DONE]\n\n"
                return

              try:
                dEvent = json.loads(vData)
              except json.JSONDecodeError:
                continue

              vType = dEvent.get("type") or vEvent

              if vType == "message_start":
                dMessage = dEvent.get("message", {})
                vResponseModel = dMessage.get("model", vResponseModel)
                vId = dMessage.get("id", vId)
                vCreated = int(time.time())
                continue

              if vType == "content_block_delta":
                dDelta = dEvent.get("delta", {})
                vText = dDelta.get("text")
                if vText:
                  yield fCreateChunk({"content": vText})
                continue

              if vType == "message_delta":
                dDelta = dEvent.get("delta", {})
                vStopReason = dDelta.get("stop_reason")
                vFinishReason = self._mMapAnthropicStopReason(vStopReason) or vFinishReason
                continue

              if vType == "message_stop":
                yield fCreateChunk({}, vFinishReason or "stop")
                yield b"data: [DONE]\n\n"
                return

              if vType == "error":
                vError = dEvent.get("error", {}).get("message") or vData
                raise Exception(f"LLM API error: {vError}")
      finally:
        await vClient.aclose()

      yield fCreateChunk({}, vFinishReason or "stop")
      yield b"data: [DONE]\n\n"

    return LlmStreamingResult(
      is_streaming=True,
      response=fGenerateStream(),
      model=pModel,
      provider=self._vProviderName
    )

  async def mCheckHealth(self) -> bool:
    """Checks whether the LLM endpoint can be reached"""
    try:
      from urllib.parse import urlparse
      vParsed = urlparse(self._vUrl)
      vBaseUrl = f"{vParsed.scheme}://{vParsed.netloc}"
      async with httpx.AsyncClient(timeout=5.0) as vClient:
        vResponse = await vClient.get(vBaseUrl)
        return vResponse.status_code < 500
    except Exception:
      return False

  def mGetInfo(self) -> dict:
    return {
      "name": self._vProviderName,
      "format": self._vFormat,
      "url": self._vUrl
    }
