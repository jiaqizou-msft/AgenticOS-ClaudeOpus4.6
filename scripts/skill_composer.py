#!/usr/bin/env python3
"""AgenticOS Skill Composer — Dynamic intent → skill decomposition.

Given a natural language request, the composer either:
1. Matches a pre-defined recipe (fast, no LLM)
2. Uses the LLM to decompose the intent into an ordered skill chain

The result is a SkillPlan — an ordered list of skills with parameters
that can be executed sequentially by the skill runner.

Usage:
    from skill_composer import SkillComposer
    composer = SkillComposer(token="...")
    plan = composer.compose("Turn brightness to 100%")
    # plan.skills = [("open_quick_settings", {}), ("set_slider", {"name":"Brightness","value":100}), ("close_panel", {})]
"""

from __future__ import annotations

import json
import os
import re
import time
from dataclasses import dataclass, field
from typing import Any

from skill_library import SKILLS, RECIPES, get_skill_catalog, Skill, Recipe


@dataclass
class SkillStep:
    """A single step in a skill plan."""
    skill_id: str
    params: dict[str, Any]
    description: str = ""

    def to_dict(self) -> dict:
        return {"skill_id": self.skill_id, "params": self.params, "description": self.description}


@dataclass
class SkillPlan:
    """An ordered plan of skills to execute."""
    intent: str                      # Original user intent
    steps: list[SkillStep]           # Ordered skill steps
    source: str = "llm"             # "recipe", "llm", "manual"
    recipe_id: str | None = None    # If matched a recipe
    confidence: float = 1.0
    created_at: float = 0.0

    def summary(self) -> str:
        chain = " → ".join(
            f"{s.skill_id}({', '.join(f'{k}={v}' for k, v in s.params.items())})"
            for s in self.steps
        )
        return f"[{self.source}] {chain}"

    def to_dict(self) -> dict:
        return {
            "intent": self.intent,
            "steps": [s.to_dict() for s in self.steps],
            "source": self.source,
            "recipe_id": self.recipe_id,
            "confidence": self.confidence,
            "created_at": self.created_at,
        }


# ── Keyword matchers for recipe selection (no LLM needed) ────────────────

INTENT_PATTERNS: list[tuple[str, str, dict]] = [
    # (regex_pattern, recipe_id, extra_params_extractor)
    # Brightness
    (r"(?:set|turn|change|adjust).*brightness.*?(\d+)", "set_brightness",
     {"_extract": lambda m: {"value": int(m.group(1))}}),
    (r"brightness.*?(\d+)%?", "set_brightness",
     {"_extract": lambda m: {"value": int(m.group(1))}}),
    (r"max(?:imize|imum)?.*brightness", "set_brightness",
     {"_extract": lambda m: {"value": 100}}),

    # Volume
    (r"(?:set|turn|change|adjust).*volume.*?(\d+)", "set_volume",
     {"_extract": lambda m: {"value": int(m.group(1))}}),
    (r"volume.*?(\d+)%?", "set_volume",
     {"_extract": lambda m: {"value": int(m.group(1))}}),
    (r"mute|silence", "set_volume",
     {"_extract": lambda m: {"value": 0}}),

    # Notepad
    (r"(?:open|launch)\s+notepad.*(?:type|write)\s+[\"']?(.+?)[\"']?\s*$", "notepad_hello_world",
     {"_extract": lambda m: {"text": m.group(1)}}),
    (r"(?:type|write)\s+[\"']?(.+?)[\"']?\s+(?:in|into)\s+notepad", "notepad_hello_world",
     {"_extract": lambda m: {"text": m.group(1)}}),

    # Calculator
    (r"(?:calculate|compute|what is)\s+(\d+\s*[\+\-\*\/x×÷]\s*\d+)", "calculator_add",
     {"_extract": lambda m: {"expression": m.group(1).replace("×", "*").replace("÷", "/").replace("x", "*")}}),

    # Settings
    (r"(?:open|go to|show).*settings.*about", "open_settings_about",
     {"_extract": lambda m: {}}),
]


class SkillComposer:
    """Decomposes natural language intents into skill plans.
    
    Strategy:
    1. Try keyword/regex matching against known recipes (instant, no LLM)
    2. Fall back to LLM-based decomposition using the skill catalog
    """

    def __init__(self, token: str = "", api_base: str = "", api_version: str = ""):
        self._token = token
        self._api_base = api_base or "https://bugtotest-resource.cognitiveservices.azure.com/"
        self._api_version = api_version or "2024-12-01-preview"

    def compose(self, intent: str, use_llm: bool = True) -> SkillPlan:
        """Decompose an intent into a skill plan.
        
        Args:
            intent: Natural language description of what to do
            use_llm: Whether to use LLM for decomposition (False = recipe-only)
        
        Returns:
            SkillPlan with ordered skill steps
        """
        # 1. Try recipe matching (fast path)
        plan = self._match_recipe(intent)
        if plan:
            return plan

        # 2. Try direct skill matching (single-skill intents)
        plan = self._match_single_skill(intent)
        if plan:
            return plan

        # 3. LLM-based decomposition
        if use_llm and self._token:
            return self._llm_decompose(intent)

        # 4. Fallback: return empty plan
        return SkillPlan(
            intent=intent,
            steps=[],
            source="none",
            confidence=0.0,
            created_at=time.time(),
        )

    def _match_recipe(self, intent: str) -> SkillPlan | None:
        """Match intent against known recipes using regex patterns."""
        intent_lower = intent.lower().strip()

        for pattern, recipe_id, meta in INTENT_PATTERNS:
            match = re.search(pattern, intent_lower, re.IGNORECASE)
            if match and recipe_id in RECIPES:
                recipe = RECIPES[recipe_id]
                extract_fn = meta.get("_extract", lambda m: {})
                extracted_params = extract_fn(match)

                steps = []
                for skill_id, base_params in recipe.skills:
                    merged = dict(base_params)
                    # Merge extracted params into skills that need them
                    if skill_id == "set_slider" and "value" in extracted_params:
                        merged["value"] = extracted_params["value"]
                    elif "text" in extracted_params and skill_id in ("notepad_type", "type_text"):
                        merged["text"] = extracted_params["text"]
                    elif "expression" in extracted_params and skill_id == "calculator_compute":
                        merged["expression"] = extracted_params["expression"]
                    steps.append(SkillStep(skill_id=skill_id, params=merged))

                return SkillPlan(
                    intent=intent,
                    steps=steps,
                    source="recipe",
                    recipe_id=recipe_id,
                    confidence=0.95,
                    created_at=time.time(),
                )

        return None

    def _match_single_skill(self, intent: str) -> SkillPlan | None:
        """Try to match a single-skill intent directly."""
        intent_lower = intent.lower().strip()

        # Simple keyword matching for common single-skill intents
        single_matches = [
            (r"open\s+(?:the\s+)?quick\s*settings", "open_quick_settings", {}),
            (r"show\s+(?:the\s+)?desktop|minimize\s+(?:all\s+)?windows?", "show_desktop", {}),
            (r"open\s+(?:the\s+)?task\s*manager", "open_task_manager", {}),
            (r"open\s+(?:the\s+)?(?:file\s+)?explorer", "open_explorer", {}),
            (r"open\s+(?:the\s+)?notepad", "open_notepad", {}),
            (r"open\s+(?:the\s+)?calculator", "open_calculator", {}),
            (r"close\s+(?:the\s+)?(?:current\s+)?window", "close_window", {}),
            (r"new\s+(?:browser\s+)?tab", "browser_new_tab", {}),
            (r"close\s+(?:this\s+)?tab", "browser_close_tab", {}),
            (r"press\s+escape|dismiss|close\s+panel", "close_panel", {}),
        ]

        for pattern, skill_id, params in single_matches:
            if re.search(pattern, intent_lower):
                return SkillPlan(
                    intent=intent,
                    steps=[SkillStep(skill_id=skill_id, params=params)],
                    source="single_match",
                    confidence=0.90,
                    created_at=time.time(),
                )

        return None

    def _llm_decompose(self, intent: str) -> SkillPlan:
        """Use LLM to decompose a complex intent into skills."""
        import litellm

        catalog = get_skill_catalog()

        prompt = f"""You are a skill planner for desktop automation.
Given a user intent and a catalog of available atomic skills, decompose the intent
into an ordered sequence of skill calls.

SKILL CATALOG:
{catalog}

USER INTENT: {intent}

Respond with ONLY a JSON array of skill steps. Each step has:
- "skill_id": the skill identifier from the catalog
- "params": a dict of parameters for that skill

Example response:
[
  {{"skill_id": "open_quick_settings", "params": {{}}}},
  {{"skill_id": "set_slider", "params": {{"name": "Brightness", "value": 100}}}},
  {{"skill_id": "close_panel", "params": {{}}}}
]

RULES:
1. Use ONLY skills from the catalog above
2. Include ALL necessary steps (don't skip setup steps like opening panels)
3. Include a close/cleanup step if you opened a panel or dialog
4. Keep the plan minimal — don't add unnecessary steps
5. Return ONLY the JSON array, no other text

Decompose the intent into skills:"""

        try:
            resp = litellm.completion(
                model="azure/gpt-4o",
                messages=[{"role": "user", "content": prompt}],
                max_tokens=500,
                temperature=0.0,
                azure_ad_token=self._token,
                api_base=self._api_base,
                api_version=self._api_version,
            )
            content = resp.choices[0].message.content.strip()
            tokens = resp.usage.total_tokens

            # Parse JSON array
            # Handle markdown code blocks
            m = re.search(r'```(?:json)?\s*(\[.*\])\s*```', content, re.DOTALL)
            if m:
                content = m.group(1)

            steps_data = json.loads(content)
            steps = []
            for s in steps_data:
                skill_id = s.get("skill_id", "")
                params = s.get("params", {})
                if skill_id in SKILLS:
                    steps.append(SkillStep(
                        skill_id=skill_id,
                        params=params,
                        description=SKILLS[skill_id].description,
                    ))

            return SkillPlan(
                intent=intent,
                steps=steps,
                source="llm",
                confidence=0.80,
                created_at=time.time(),
            )

        except Exception as e:
            print(f"[SkillComposer] LLM decomposition error: {e}")
            return SkillPlan(
                intent=intent,
                steps=[],
                source="llm_error",
                confidence=0.0,
                created_at=time.time(),
            )

    def compose_from_skills(self, skill_specs: list[str]) -> SkillPlan:
        """Create a plan from explicit skill specifications.
        
        Format: ["skill_id:param1:value1:param2:value2", ...]
        Example: ["open_quick_settings", "set_slider:name:Brightness:value:100", "close_panel"]
        """
        steps = []
        for spec in skill_specs:
            parts = spec.split(":")
            skill_id = parts[0]
            params = {}
            for i in range(1, len(parts) - 1, 2):
                key = parts[i]
                val = parts[i + 1]
                # Try to parse as int/float
                try:
                    val = int(val)
                except ValueError:
                    try:
                        val = float(val)
                    except ValueError:
                        pass
                params[key] = val

            if skill_id in SKILLS:
                steps.append(SkillStep(skill_id=skill_id, params=params))
            else:
                print(f"[SkillComposer] Unknown skill: {skill_id}")

        return SkillPlan(
            intent=f"manual: {', '.join(skill_specs)}",
            steps=steps,
            source="manual",
            confidence=1.0,
            created_at=time.time(),
        )


if __name__ == "__main__":
    # Test the composer with various intents
    composer = SkillComposer()

    test_intents = [
        "Turn brightness to 100%",
        "Set volume to 50%",
        "Set brightness to 75% and volume to 30%",
        "Open notepad and type Hello World",
        "Calculate 123 + 456",
        "Open Settings about page",
        "Show the desktop",
        "Open Task Manager",
        "Mute the volume",
        "Maximize brightness",
    ]

    for intent in test_intents:
        plan = composer.compose(intent, use_llm=False)  # Recipe-only mode
        if plan.steps:
            print(f"✓ '{intent}' → {plan.summary()}")
        else:
            print(f"✗ '{intent}' → no recipe match (would use LLM)")
