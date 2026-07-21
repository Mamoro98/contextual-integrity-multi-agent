"""Shared helpers for the shared-context scenario generator."""
import json
import re

# PrivacyLens Surgery-Kit banned words (test_no_explicit_word) + our extras.
# Nothing agent-visible may flag information as sensitive or shareable --
# the assistant must infer the norm on its own (anti-priming rule).
BANNED_WORDS = [
    # PrivacyLens originals
    "sensitive", "private", "privacy", "confident", "secret",
    # our extensions (bugs we hand-fixed in the MVP scenario)
    "worth sharing", "keep between", "keep this between", "discreet",
    "do not share", "don't share", "not to share", "off the record",
    # disclosure-judgment phrases (the story/scenario must state facts,
    # never verdicts about what should or shouldn't be shared).
    # "appropriate" also catches "inappropriate" as a substring.
    "appropriate", "should not be shared", "must not be shared",
    "should not be disclosed", "must not be disclosed",
    "safe to share", "fine to share", "free to share",
]


def find_banned_words(text):
    """Return the banned words present in text (case-insensitive)."""
    low = text.lower()
    return [w for w in BANNED_WORDS if w in low]


def extract_json(text):
    """Parse the first {...} block out of an LLM reply.

    Tolerates markdown fences and stray prose around the object.
    Raises ValueError if nothing parseable is found.
    """
    # extract only the json {} --> in regex {} means repitition
    # a{3} == aaa. so bracetes must be escaped with \{ and \} 
    # .* means anything. So all means { everything inside } --> 
    # this is how to get the json file
    m = re.search(r"\{.*\}", text, re.DOTALL)
    if not m:
        raise ValueError(f"no JSON object in LLM reply: {text[:200]!r}")
    return json.loads(m.group(0))

# temp = 0.7 because we are trying to invent things (names, stories..etc)
def sample_json(model, prompt, max_tokens=1500, temperature=0.7, tries=3):
    """Call the model until it returns parseable JSON (up to `tries`)."""
    last_err = None
    for _ in range(tries):
        ans = model.sample_text(prompt, max_tokens=max_tokens, temperature=temperature)
        try:
            return extract_json(ans)
        except (ValueError, json.JSONDecodeError) as e:
            last_err = e
    raise RuntimeError(f"model never returned valid JSON: {last_err}")
