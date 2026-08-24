"""Input moderation that runs BEFORE the LLM (guardrail as a separate step).

A prompt-injection / system-prompt-extraction / model-disclosure attempt is
caught here and answered with a canned refusal, so a jailbroken prompt never
reaches generation and has nothing to stream (the pattern observed in the
Zalando teardown: a first-class BLOCKED with zero model text).

Deliberately conservative: patterns require the request to target the assistant
itself (its prompt / instructions / model), so ordinary shop language like
"which model do you recommend?" is NOT blocked.
"""

import re

# Canned reply for a blocked message — stays on-task and reveals nothing.
BLOCKED_REPLY = (
    "Ich kann dir gern bei der Produktsuche helfen, gebe aber keine internen "
    "System- oder Modellinformationen preis. Wonach für ein Produkt suchst du?"
)

_PATTERNS = [
    # override / ignore instructions
    r"\b(ignore|disregard|forget|override|bypass)\b.{0,30}\b(previous|above|prior|all|your|the)?\s*(instructions?|rules?|prompt|guidelines?)\b",
    # extract the system prompt / rules
    r"\bsystem\s*prompt\b",
    r"\b(reveal|show|print|repeat|display|expose|leak|tell me|give me)\b.{0,30}\b(system\s*prompt|prompt|instructions?|rules?|guidelines?)\b",
    r"\binitial\s*(prompt|instructions?)\b",
    r"\brepeat (the )?(text|words|everything) above\b",
    # disclose the model / vendor (targeted at the assistant, not products)
    r"\bwhat\s+(ai|llm|language\s*model|model)\s+are\s+you\b",
    r"\bwhich\s+(ai|llm|language\s*model|model)\b.{0,20}\b(are\s+you|do\s+you\s+use|powers?\s+you|is\s+this)\b",
    r"\b(are|is)\s+you\b.{0,15}\b(chatgpt|gpt-?\d?|mistral|claude|gemini|llama|bard|openai|anthropic)\b",
    r"\bwelches?\s+(ki|ai|sprachmodell|modell)\b.{0,20}\b(bist du|nutzt du|verwendest du|steckt)\b",
    r"\b(dein|euer)\s+system\s*prompt\b",
    r"\b(zeig|verrate|nenne)\b.{0,30}\b(system\s*prompt|anweisungen|regeln)\b",
    # jailbreak framings
    r"\bjailbreak\b", r"\bdeveloper mode\b", r"\bDAN\b", r"\bprompt injection\b",
]
_RE = [re.compile(p, re.IGNORECASE) for p in _PATTERNS]


def blocked_reason(message: str) -> str | None:
    """Return a short reason if the message should be blocked pre-generation, else None."""
    if not message:
        return None
    for rx in _RE:
        if rx.search(message):
            return f"input matched guardrail pattern: {rx.pattern[:40]}"
    return None
