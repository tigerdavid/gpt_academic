"""
Token & Cost Tracker - Real-time token usage and cost estimation.

Tracks input/output tokens per conversation and estimates API costs.
Integrates with the chat flow via hooks in bridge_all.py.
"""

import tiktoken
from functools import lru_cache
from typing import Optional, Dict, List
from loguru import logger


# Pricing per 1M tokens (USD)
MODEL_PRICING = {
    "deepseek-v4-flash":     {"input": 0.14, "output": 0.28, "cache_hit": 0.028},
    "deepseek-v4-pro":       {"input": 1.74, "output": 3.48, "cache_hit": 0.145},
    "deepseek-chat":         {"input": 0.14, "output": 0.28},
    "deepseek-reasoner":     {"input": 0.55, "output": 2.19},
    "gpt-4o":                {"input": 2.50, "output": 10.00},
    "gpt-4o-mini":           {"input": 0.15, "output": 0.60},
    "gpt-4.1":               {"input": 2.00, "output": 8.00},
    "gpt-4.1-mini":          {"input": 0.40, "output": 1.60},
    "o4-mini":               {"input": 1.10, "output": 4.40},
    "o3":                    {"input": 10.00, "output": 40.00},
    "claude-sonnet-4-6":     {"input": 3.00, "output": 15.00},
    "claude-haiku-4-5":      {"input": 0.80, "output": 4.00},
    "claude-opus-4-6":       {"input": 15.00, "output": 75.00},
    "gemini-2.0-flash":      {"input": 0.10, "output": 0.40},
    "gemini-2.5-pro":        {"input": 1.25, "output": 10.00},
    "qwen-max":              {"input": 0.40, "output": 1.20},
    "glm-4":                 {"input": 0.10, "output": 0.10},
    "moonshot-v1-128k":      {"input": 0.06, "output": 0.06},
}


class TokenCostTracker:
    """Per-session token and cost tracker."""

    def __init__(self):
        self.total_input_tokens = 0
        self.total_output_tokens = 0
        self.total_cost = 0.0
        self.request_count = 0
        self._tokenizer = None

    @property
    def tokenizer(self):
        if self._tokenizer is None:
            self._tokenizer = self._get_tokenizer()
        return self._tokenizer

    @staticmethod
    @lru_cache(maxsize=1)
    def _get_tokenizer():
        return tiktoken.encoding_for_model("gpt-4")

    def count_tokens(self, text: str) -> int:
        """Count tokens in a text string."""
        if not text:
            return 0
        try:
            return len(self.tokenizer.encode(text))
        except Exception:
            return len(text) // 4  # rough fallback

    def get_pricing(self, model_name: str) -> dict:
        """Get pricing for a model. Supports partial name matching."""
        # Exact match
        if model_name in MODEL_PRICING:
            return MODEL_PRICING[model_name]

        # Partial match (e.g., "deepseek/deepseek-v4-pro" -> "deepseek-v4-pro")
        short_name = model_name.split("/")[-1] if "/" in model_name else model_name
        if short_name in MODEL_PRICING:
            return MODEL_PRICING[short_name]

        # Fuzzy match
        for known in MODEL_PRICING:
            if known in model_name or model_name in known:
                return MODEL_PRICING[known]

        return {"input": 0, "output": 0}  # unknown model

    def track_request(
        self,
        model: str,
        input_tokens: int,
        output_tokens: int = 0,
    ) -> Dict:
        """Record a request and return cost summary."""
        self.total_input_tokens += input_tokens
        self.total_output_tokens += output_tokens
        self.request_count += 1

        pricing = self.get_pricing(model)
        cost = (input_tokens / 1_000_000) * pricing["input"] + \
               (output_tokens / 1_000_000) * pricing["output"]
        self.total_cost += cost

        return {
            "model": model,
            "input_tokens": input_tokens,
            "output_tokens": output_tokens,
            "cost": cost,
            "request_num": self.request_count,
        }

    def get_summary(self, model: str = None) -> str:
        """Get a human-readable summary of token usage and cost."""
        if self.total_input_tokens == 0 and self.total_output_tokens == 0:
            return ""

        lines = [
            f"📊 **Token 用量统计** (本次会话第 {self.request_count} 次请求)",
            f"",
            f"| 项目 | 数量 |",
            f"|------|------|",
            f"| 输入 tokens | {self.total_input_tokens:,} |",
            f"| 输出 tokens | {self.total_output_tokens:,} |",
            f"| 总计 tokens | {self.total_input_tokens + self.total_output_tokens:,} |",
        ]

        if self.total_cost > 0:
            lines.append(f"| 预估费用 | ${self.total_cost:.4f} (≈¥{self.total_cost * 7.2:.2f}) |")

        return "\n".join(lines)

    def get_cost_html(self, model: str = None) -> str:
        """Get a compact HTML cost badge for the last request."""
        if self.total_cost <= 0:
            return ""

        return (
            f'<div style="margin-top:0.5em; padding:0.4em 0.8em; '
            f'background:#1a1a2e; border-radius:6px; font-size:0.85em; color:#a0a0b0;">'
            f'💰 本次: {self.total_input_tokens + self.total_output_tokens:,} tokens · '
            f'${self.total_cost:.4f} (≈¥{self.total_cost * 7.2:.2f})'
            f'</div>'
        )


# Global tracker instance
_tracker: Optional[TokenCostTracker] = None


def get_tracker() -> TokenCostTracker:
    """Get or create the global token tracker."""
    global _tracker
    if _tracker is None:
        _tracker = TokenCostTracker()
    return _tracker


def reset_tracker():
    """Reset the global tracker (for new conversations)."""
    global _tracker
    _tracker = TokenCostTracker()


def count_input_tokens(messages: List[Dict]) -> int:
    """Count tokens in a list of messages."""
    tracker = get_tracker()
    total = 0
    for msg in messages:
        if isinstance(msg, dict):
            total += tracker.count_tokens(str(msg.get("content", "")))
        elif isinstance(msg, str):
            total += tracker.count_tokens(msg)
    return total


def count_output_tokens(text: str) -> int:
    """Count tokens in output text."""
    return get_tracker().count_tokens(text)
