from __future__ import annotations

import os
import re

from google import genai
from google.genai import types

from ..models.review import Finding, ReviewResult
from .prompts import SYSTEM_PROMPT, USER_TEMPLATE

_SEVERITIES = ("critical", "warning", "info", "suggestion")
_NULLABLE = ("", "unknown", "none")


class LLMClient:
    def __init__(self, model_name="gemini-2.5-flash", api_key=None, temperature=0.2):
        key = api_key if api_key is not None else os.environ.get("GEMINI_API_KEY")
        if not key:
            raise RuntimeError("GEMINI_API_KEY is not set")
        self.client = genai.Client(api_key=key)
        self.model_name = model_name
        self.config = types.GenerateContentConfig(
            system_instruction=SYSTEM_PROMPT,
            temperature=temperature,
        )

    def review(self, context: str, query: str) -> ReviewResult:
        user = USER_TEMPLATE.format(query=query, context=context)
        response = self.client.models.generate_content(
            model=self.model_name,
            contents=user,
            config=self.config,
        )
        return self._parse(response.text)

    def review_stream(self, context: str, query: str):
        user = USER_TEMPLATE.format(query=query, context=context)
        for chunk in self.client.models.generate_content_stream(
            model=self.model_name,
            contents=user,
            config=self.config,
        ):
            if chunk.text:
                yield chunk.text

    def _parse(self, text: str) -> ReviewResult:
        lines = text.splitlines()
        findings: list[Finding] = []
        summary = ""
        i = 0
        n = len(lines)
        while i < n:
            stripped = lines[i].strip()
            if stripped == "SUMMARY:":
                summary = "\n".join(lines[i + 1:]).strip()
                break
            if stripped == "FINDING:":
                i += 1
                fields: dict[str, str] = {}
                while i < n:
                    current = lines[i].strip()
                    if current in ("", "FINDING:", "SUMMARY:"):
                        break
                    if ":" in current:
                        key, _, value = current.partition(":")
                        fields[key.strip().lower()] = value.strip()
                    i += 1
                findings.append(self._build_finding(fields))
                continue
            i += 1
        if not findings:
            return ReviewResult(summary=text, findings=[], raw=text)
        return ReviewResult(summary=summary, findings=findings, raw=text)

    def _build_finding(self, fields: dict) -> Finding:
        severity = fields.get("severity", "").strip().lower()
        if severity not in _SEVERITIES:
            severity = "info"
        return Finding(
            severity=severity,
            file_path=self._clean(fields.get("file")),
            line_range=self._parse_lines(fields.get("lines")),
            description=fields.get("description", ""),
            suggestion=self._clean(fields.get("suggestion")),
        )

    def _clean(self, value):
        if value is None:
            return None
        stripped = value.strip()
        if stripped.lower() in _NULLABLE:
            return None
        return stripped

    def _parse_lines(self, value):
        if value is None:
            return None
        if value.strip().lower() in _NULLABLE:
            return None
        match = re.match(r"\s*(\d+)\s*-\s*(\d+)", value)
        if match:
            return (int(match.group(1)), int(match.group(2)))
        return None
