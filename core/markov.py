from __future__ import annotations
"""Markov chain text generator built from Discord chat logs."""

import random
import re
import math
import logging
from datetime import datetime, timezone
from collections import defaultdict
from core import database

logger = logging.getLogger(__name__)

# Words that indicate an incomplete sentence ending
_INCOMPLETE_ENDINGS = {
    "the", "a", "an", "and", "or", "but", "so", "if", "to", "of", "in",
    "for", "on", "with", "at", "by", "from", "is", "are", "was", "were",
    "be", "been", "being", "have", "has", "had", "do", "does", "did",
    "will", "would", "could", "should", "can", "may", "might", "shall",
    "not", "my", "your", "his", "her", "our", "their", "its", "this",
    "that", "these", "those", "than", "as", "into", "about", "just",
    "very", "really", "also", "even", "still", "when", "where", "while",
    "because", "since", "until", "before", "after", "during", "between",
    "through", "im", "i", "you", "we", "they", "he", "she", "it",
}

# Leading conjunctions/filler to strip from output
_LEADING_STRIP = {"and", "but", "so", "or", "also", "then", "like", "well"}


class MarkovChain:
    """
    N-gram Markov chain text generator.
    Builds transition probabilities from chat messages and generates
    text that sounds like the server's actual conversations.
    """

    def __init__(self, order: int = 3):
        """
        Args:
            order: Number of words to use as context (higher = more coherent
                   but more likely to copy exact messages). 3 is a good sweet spot.
        """
        self.order = order
        self.chain: dict[tuple[str, ...], list[str]] = defaultdict(list)
        self.chain_o2: dict[tuple[str, ...], list[str]] = defaultdict(list)  # Order-2 fallback
        self.starters: list[tuple[str, ...]] = []  # Sentence starters
        self._built = False
        self._message_count = 0

    @property
    def is_built(self) -> bool:
        return self._built

    @property
    def message_count(self) -> int:
        return self._message_count

    async def build_from_database(
        self, guild_id: int, read_channels: list[int] | None = None
    ) -> None:
        """
        Build the Markov chain from messages in the database.

        Args:
            guild_id: The Discord guild ID.
            read_channels: Optional list of channel IDs to read from.
        """
        # Get ALL messages (not just a sample) for the Markov chain
        messages = await database.get_random_sample(
            guild_id=guild_id,
            n=50000,  # Get as many as possible
            read_channels=read_channels,
        )

        if not messages:
            logger.warning("No messages found for guild %s — Markov chain empty", guild_id)
            return

        # Include boosted messages — each boost adds the message again
        # so its word patterns become more likely in the chain
        boosts = await database.get_boosted_messages(guild_id)
        boost_count = 0
        for content, count in boosts:
            # Add the message multiple times based on boost (capped at 5x)
            repeats = min(count, 5)
            for _ in range(repeats):
                messages.append({"content": content, "author_name": "retep"})
                boost_count += 1

        self._build_chain(messages)
        logger.info(
            "Markov chain built for guild %s: %d messages (+%d boosts), "
            "%d unique states (order=%d), %d order-2 states",
            guild_id,
            self._message_count,
            boost_count,
            len(self.chain),
            self.order,
            len(self.chain_o2),
        )

    def _build_chain(self, messages: list[dict]) -> None:
        """Build the transition table from a list of message dicts.
        
        Applies logarithmic recency weighting: recent messages get up to +15%
        more influence, oldest messages get -15%.
        """
        self.chain.clear()
        self.chain_o2.clear()
        self.starters.clear()
        self._message_count = 0
        self._originals: set[str] = set()  # For detecting verbatim copies

        # Calculate recency weights for all messages
        now = datetime.now(timezone.utc)
        ages = []  # (index, age_days)
        for i, msg in enumerate(messages):
            ts_str = msg.get("timestamp")
            if ts_str:
                try:
                    # Handle various timestamp formats
                    ts = datetime.fromisoformat(ts_str.replace("Z", "+00:00"))
                    if ts.tzinfo is None:
                        ts = ts.replace(tzinfo=timezone.utc)
                    age = (now - ts).total_seconds() / 86400  # age in days
                    ages.append((i, max(age, 0)))
                except (ValueError, TypeError):
                    ages.append((i, None))
            else:
                ages.append((i, None))

        # Find max age for normalization
        valid_ages = [a for _, a in ages if a is not None]
        max_age = max(valid_ages) if valid_ages else 1.0
        if max_age == 0:
            max_age = 1.0

        for msg_idx, msg in enumerate(messages):
            content = msg["content"].strip()
            if not content:
                continue

            # Skip URLs-only messages, bot commands
            if content.startswith(("http://", "https://", "!", "/")):
                continue

            self._message_count += 1
            # Store normalized version for dedup
            self._originals.add(content.lower())
            words = content.split()

            if len(words) < self.order:
                continue

            # Calculate recency weight: log curve from 1.15 (newest) to 0.85 (oldest)
            _, age = ages[msg_idx] if msg_idx < len(ages) else (None, None)
            if age is not None:
                ratio = age / max_age  # 0 = newest, 1 = oldest
                # Logarithmic curve: log(1 + ratio*(e-1)) maps [0,1] -> [0,1] with log shape
                log_ratio = math.log1p(ratio * (math.e - 1))  # 0 to 1, log-curved
                weight = 1.15 - 0.30 * log_ratio  # 1.15 down to 0.85
            else:
                weight = 1.0  # No timestamp = neutral weight

            # Record the sentence starter
            starter = tuple(words[: self.order])
            self.starters.append(starter)

            # Build order-3 transitions
            for i in range(len(words) - self.order):
                state = tuple(words[i : i + self.order])
                next_word = words[i + self.order]
                self.chain[state].append(next_word)

            # Build order-2 transitions (for fallback)
            for i in range(len(words) - 2):
                state_o2 = tuple(words[i : i + 2])
                next_word = words[i + 2]
                self.chain_o2[state_o2].append(next_word)

            # Recency bonus: add transitions again with probability (weight - 1.0)
            # For weight > 1.0 (recent): chance to double transitions
            # For weight < 1.0 (old): we already added once, no extra
            if weight > 1.0 and random.random() < (weight - 1.0):
                # Add bonus transitions for recent messages
                self.starters.append(starter)
                for i in range(len(words) - self.order):
                    state = tuple(words[i : i + self.order])
                    next_word = words[i + self.order]
                    self.chain[state].append(next_word)
                for i in range(len(words) - 2):
                    state_o2 = tuple(words[i : i + 2])
                    next_word = words[i + 2]
                    self.chain_o2[state_o2].append(next_word)
            elif weight < 1.0 and random.random() > weight:
                # Remove the transitions we just added for very old messages
                self.starters.pop()
                for i in range(len(words) - self.order):
                    state = tuple(words[i : i + self.order])
                    if self.chain[state]:
                        self.chain[state].pop()
                for i in range(len(words) - 2):
                    state_o2 = tuple(words[i : i + 2])
                    if self.chain_o2[state_o2]:
                        self.chain_o2[state_o2].pop()

        self._built = True

    def _is_verbatim_copy(self, text: str) -> bool:
        """Check if generated text is a verbatim copy of an original message."""
        return text.lower() in self._originals

    def generate(
        self,
        max_words: int = 35,
        seed_text: str | None = None,
        candidates: int = 20,
    ) -> str:
        """
        Generate text using the Markov chain with best-of-N selection.

        Generates multiple candidates and picks the best one based on
        natural endings, sentence completeness, length, and seed relevance.

        Args:
            max_words: Maximum number of words to generate.
            seed_text: Optional text to seed generation with relevant starting point.
            candidates: Number of candidates to generate and pick the best from.

        Returns:
            Generated text string.
        """
        if not self._built or not self.starters:
            return ""

        # Find multiple diverse seed states for variety across candidates
        seed_states = []
        if seed_text:
            seed_states = self._find_seed_states(seed_text, n=candidates // 2)

        # Generate multiple candidates — no hard min_words, let scoring decide
        results = []
        for i in range(candidates):
            # Alternate between seed states and random starters for diversity
            if seed_states and i < len(seed_states):
                state = seed_states[i]
            elif seed_states:
                state = random.choice(seed_states)
            else:
                state = random.choice(self.starters)

            text = self._generate_once(state, max_words)
            if text:
                text = self._clean_output(text)
                if text and not self._is_verbatim_copy(text):
                    results.append(text)

        if not results:
            # Fallback: just generate one without filtering
            state = random.choice(self.starters)
            text = self._generate_once(state, max_words)
            return self._clean_output(text) if text else ""

        # Score and pick the best candidate, with relevance bonus for seeded queries
        scored = [(self._score_text(t, seed_text=seed_text), t) for t in results]
        scored.sort(key=lambda x: x[0], reverse=True)

        return scored[0][1]

    def generate_multi_sentence(
        self,
        max_sentences: int = 3,
        seed_text: str | None = None,
    ) -> str:
        """
        Generate a multi-sentence response with bell curve distribution.
        Usually 1 sentence, sometimes 2, rarely 3.

        Args:
            max_sentences: Maximum number of sentences.
            seed_text: Optional text to seed generation with relevant starting point.

        Returns:
            Multi-sentence generated text.
        """
        # Bell curve: usually 1, sometimes 2, rarely 3
        count = max(1, min(max_sentences, round(random.gauss(1.3, 0.6))))

        sentences = []
        for i in range(count):
            # Only use seed text for the first sentence
            text = self.generate(
                max_words=25,
                seed_text=seed_text if i == 0 else None,
                candidates=20,
            )
            if text and text not in sentences:  # avoid duplicate sentences
                sentences.append(text)

        return " ".join(sentences)

    def _generate_once(self, state: tuple[str, ...], max_words: int = 35) -> str:
        """Single generation from a given starting state, with order-2 fallback."""
        words = list(state)

        for _ in range(max_words - self.order):
            next_words = self.chain.get(state)

            # Order-2 fallback: if order-3 has no transitions, try order-2
            if not next_words:
                state_o2 = tuple(words[-2:])
                next_words = self.chain_o2.get(state_o2)
                if not next_words:
                    break

            next_word = random.choice(next_words)
            words.append(next_word)
            state = tuple(words[-self.order :])

            # Stop at natural sentence endings (sometimes)
            if self._is_natural_ending(next_word) and len(words) >= 6:
                # 70% chance to stop at a natural ending
                if random.random() < 0.7:
                    break

        return " ".join(words)

    @staticmethod
    def _clean_output(text: str) -> str:
        """Clean up generated text: fix capitalization, strip leading conjunctions."""
        if not text:
            return text

        words = text.split()
        if not words:
            return text

        # Strip leading conjunctions/filler words
        while len(words) > 2 and words[0].lower() in _LEADING_STRIP:
            words.pop(0)

        # Capitalize first letter
        if words:
            first = words[0]
            if first and first[0].isalpha():
                words[0] = first[0].upper() + first[1:]

        return " ".join(words)

    @staticmethod
    def _is_natural_ending(word: str) -> bool:
        """Check if a word represents a natural sentence ending."""
        if not word:
            return False
        # Standard punctuation endings
        if word.endswith((".", "!", "?")):
            return True
        # Check for emoji at end of word
        last = ord(word[-1])
        return (
            0x1F600 <= last <= 0x1F64F
            or 0x1F300 <= last <= 0x1F5FF
            or 0x1F680 <= last <= 0x1F6FF
            or 0x1F900 <= last <= 0x1F9FF
            or 0x2600 <= last <= 0x26FF
            or 0x2700 <= last <= 0x27BF
        )

    def _score_text(self, text: str, seed_text: str | None = None) -> float:
        """
        Score a generated text for quality.
        Higher score = better candidate.
        Optionally boosts score for relevance to seed_text.
        """
        words = text.split()
        score = 0.0

        # Prefer texts that end naturally (punctuation, emoji, or common Discord endings)
        last_word = words[-1] if words else ""
        if self._is_natural_ending(last_word):
            score += 4.0
        elif last_word.lower() in ("lol", "lmao", "tbh", "fr", "ngl", "bruh", "rip"):
            score += 3.0
        # PENALIZE incomplete endings heavily
        elif last_word.lower() in _INCOMPLETE_ENDINGS:
            score -= 5.0

        # Prefer medium length (not too short, not too long)
        word_count = len(words)
        if 5 <= word_count <= 20:
            score += 2.0
        elif 3 <= word_count <= 25:
            score += 1.0

        # Soft penalty for very short (bell curve handles odds, this nudges scoring)
        if word_count <= 2:
            score -= 1.5
        elif word_count <= 3:
            score -= 0.5

        # Slight bonus for having some variety (not just one repeated pattern)
        unique_ratio = len(set(words)) / max(len(words), 1)
        score += unique_ratio

        # Relevance bonus: if seed text was provided, reward candidates that
        # contain seed keywords (makes responses topically relevant)
        if seed_text:
            seed_words = set(seed_text.lower().split())
            stop_words = {
                "the", "a", "an", "is", "are", "was", "were", "be", "been",
                "being", "have", "has", "had", "do", "does", "did", "will",
                "would", "could", "should", "to", "of", "in", "for", "on",
                "with", "at", "by", "from", "it", "this", "that", "what",
                "you", "i", "me", "my", "we", "and", "or", "but", "not",
                "retep", "ask", "hey", "yo", "please", "tell",
            }
            content_words = seed_words - stop_words
            if content_words:
                text_words = set(w.lower() for w in words)
                overlap = text_words & content_words
                # +2 per matching keyword, rewards topical relevance
                score += len(overlap) * 2.0

        return score

    def _find_seed_state(self, seed_text: str) -> tuple[str, ...] | None:
        """
        Try to find a starting state that's relevant to the seed text.
        Uses multiple strategies: bigram matching → keyword matching → single word.
        """
        seed_words = seed_text.lower().split()
        # Remove common words that would match too broadly
        stop_words = {
            "the", "a", "an", "is", "are", "was", "were", "be", "been",
            "being", "have", "has", "had", "do", "does", "did", "will",
            "would", "could", "should", "may", "might", "can", "shall",
            "to", "of", "in", "for", "on", "with", "at", "by", "from",
            "it", "this", "that", "what", "which", "who", "how", "when",
            "where", "why", "your", "you", "i", "me", "my", "we", "our",
            "he", "she", "they", "them", "his", "her", "its", "and", "or",
            "but", "not", "no", "so", "if", "then", "than", "up", "out",
            "retep", "ask", "hey", "yo", "please", "tell",
        }
        content_words = [w for w in seed_words if w not in stop_words and len(w) > 1]

        if not content_words:
            return None

        # Strategy 1: Try to find states containing bigrams from the seed
        # (e.g., "league of" or "play tonight" → very relevant starters)
        seed_bigrams = set()
        for i in range(len(seed_words) - 1):
            seed_bigrams.add((seed_words[i], seed_words[i + 1]))

        if seed_bigrams:
            bigram_matches = []
            for state in self.chain:
                state_lower = tuple(w.lower() for w in state)
                for j in range(len(state_lower) - 1):
                    if (state_lower[j], state_lower[j + 1]) in seed_bigrams:
                        bigram_matches.append(state)
                        break
            if bigram_matches:
                return random.choice(bigram_matches)

        # Strategy 2: Find states with multiple content word matches (most relevant)
        content_set = set(content_words)
        multi_match = []
        single_match = []
        for state in self.chain:
            state_words = {w.lower() for w in state}
            overlap = state_words & content_set
            if len(overlap) >= 2:
                multi_match.extend([state] * len(overlap))
            elif len(overlap) == 1:
                single_match.extend([state] * 1)

        if multi_match:
            return random.choice(multi_match)

        # Strategy 3: Single content word match
        if single_match:
            return random.choice(single_match)

        return None

    def _find_seed_states(self, seed_text: str, n: int = 5) -> list[tuple[str, ...]]:
        """
        Find multiple relevant seed states for diversity across candidates.
        Returns up to n different seed states.
        """
        seed_words = seed_text.lower().split()
        stop_words = {
            "the", "a", "an", "is", "are", "was", "were", "be", "been",
            "being", "have", "has", "had", "do", "does", "did", "will",
            "would", "could", "should", "may", "might", "can", "shall",
            "to", "of", "in", "for", "on", "with", "at", "by", "from",
            "it", "this", "that", "what", "which", "who", "how", "when",
            "where", "why", "your", "you", "i", "me", "my", "we", "our",
            "he", "she", "they", "them", "his", "her", "its", "and", "or",
            "but", "not", "no", "so", "if", "then", "than", "up", "out",
            "retep", "ask", "hey", "yo", "please", "tell",
        }
        content_words = set(w for w in seed_words if w not in stop_words and len(w) > 1)

        if not content_words:
            return []

        # Collect all matching states with weights
        weighted = []
        for state in self.chain:
            state_words = {w.lower() for w in state}
            overlap = state_words & content_words
            if overlap:
                # Weight by overlap count squared for relevance
                weighted.extend([state] * (len(overlap) ** 2))

        if not weighted:
            return []

        # Pick n diverse states
        results = []
        seen = set()
        for _ in range(n * 3):  # oversample to get diversity
            pick = random.choice(weighted)
            key = pick  # tuple is hashable
            if key not in seen:
                seen.add(key)
                results.append(pick)
                if len(results) >= n:
                    break

        return results

    def generate_multiple(self, count: int = 5, max_words: int = 35) -> list[str]:
        """Generate multiple messages and return them all."""
        return [self.generate(max_words=max_words) for _ in range(count)]


# ── Global instance cache ────────────────────────────────────────────────────

_chains: dict[int, MarkovChain] = {}  # guild_id -> MarkovChain


async def get_chain(guild_id: int, force_rebuild: bool = False) -> MarkovChain:
    """Get or build the Markov chain for a guild."""
    if not force_rebuild and guild_id in _chains and _chains[guild_id].is_built:
        return _chains[guild_id]

    chain = MarkovChain(order=3)
    read_channels = await database.get_read_channels(guild_id)
    await chain.build_from_database(
        guild_id=guild_id,
        read_channels=read_channels if read_channels else None,
    )
    _chains[guild_id] = chain
    return chain


def invalidate_chain(guild_id: int | None = None) -> None:
    """Clear cached Markov chain(s)."""
    if guild_id is None:
        _chains.clear()
    else:
        _chains.pop(guild_id, None)
