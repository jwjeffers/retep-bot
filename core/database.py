"""SQLite database for message storage and channel configuration."""

import aiosqlite
import logging
from datetime import datetime
from typing import Optional

logger = logging.getLogger(__name__)

DB_PATH = "retep.db"

# Punctuation that counts as a valid sentence ending
_END_PUNCTUATION = frozenset(".!?")


def _ends_with_emoji(text: str) -> bool:
    """Check if text ends with a Unicode emoji or Discord custom emoji."""
    if not text:
        return False
    # Discord custom emoji: <:name:id> or <a:name:id>
    if text.endswith(">") and "<:" in text[-30:]:
        return True
    # Check last character for Unicode emoji ranges
    last = ord(text[-1])
    # Common emoji Unicode ranges
    return (
        0x1F600 <= last <= 0x1F64F  # Emoticons
        or 0x1F300 <= last <= 0x1F5FF  # Misc Symbols
        or 0x1F680 <= last <= 0x1F6FF  # Transport
        or 0x1F900 <= last <= 0x1F9FF  # Supplemental
        or 0x2600 <= last <= 0x26FF  # Misc Symbols
        or 0x2700 <= last <= 0x27BF  # Dingbats
        or 0xFE00 <= last <= 0xFE0F  # Variation selectors
        or 0x200D <= last <= 0x200D  # ZWJ
        or last == 0x20E3  # Combining enclosing keycap
    )


def normalize_content(content: str) -> str:
    """
    Normalize message content for cleaner data.
    Adds a period to messages that don't end with punctuation or emoji.
    """
    content = content.strip()
    if not content:
        return content
    # Don't add period if it already ends with punctuation
    if content[-1] in _END_PUNCTUATION:
        return content
    # Don't add period if it ends with an emoji
    if _ends_with_emoji(content):
        return content
    # Add period for everything else
    content += "."
    return content


async def init_db(db_path: str = DB_PATH) -> None:
    """Create tables if they don't exist."""
    global DB_PATH
    DB_PATH = db_path

    async with aiosqlite.connect(DB_PATH) as db:
        # Message history table
        await db.execute("""
            CREATE TABLE IF NOT EXISTS messages (
                id INTEGER PRIMARY KEY,
                channel_id INTEGER NOT NULL,
                guild_id INTEGER NOT NULL,
                author_name TEXT NOT NULL,
                author_id INTEGER NOT NULL,
                content TEXT NOT NULL,
                timestamp TEXT NOT NULL
            )
        """)

        # Channel configuration table (read list / chat list)
        await db.execute("""
            CREATE TABLE IF NOT EXISTS channel_config (
                channel_id INTEGER NOT NULL,
                guild_id INTEGER NOT NULL,
                list_type TEXT NOT NULL CHECK(list_type IN ('read', 'chat')),
                PRIMARY KEY (channel_id, list_type)
            )
        """)

        # Emoji reactions tracking table
        await db.execute("""
            CREATE TABLE IF NOT EXISTS emoji_reactions (
                message_id INTEGER NOT NULL,
                guild_id INTEGER NOT NULL,
                emoji TEXT NOT NULL,
                count INTEGER NOT NULL DEFAULT 1,
                timestamp TEXT,
                PRIMARY KEY (message_id, emoji)
            )
        """)

        # Indexes for fast lookups
        await db.execute("""
            CREATE INDEX IF NOT EXISTS idx_messages_channel
            ON messages (channel_id, timestamp)
        """)
        await db.execute("""
            CREATE INDEX IF NOT EXISTS idx_reactions_guild
            ON emoji_reactions (guild_id, timestamp)
        """)

        await db.commit()
    logger.info("Database initialized at %s", DB_PATH)


# ── Message Storage ──────────────────────────────────────────────────────────


async def store_messages(messages: list[dict]) -> int:
    """
    Store messages in bulk. Skips duplicates (by message ID).
    Each message dict should have: id, channel_id, guild_id, author_name,
    author_id, content, timestamp.
    Returns the number of new messages inserted.
    """
    if not messages:
        return 0

    inserted = 0
    async with aiosqlite.connect(DB_PATH) as db:
        for msg in messages:
            try:
                await db.execute(
                    """INSERT OR IGNORE INTO messages
                       (id, channel_id, guild_id, author_name, author_id, content, timestamp)
                       VALUES (?, ?, ?, ?, ?, ?, ?)""",
                    (
                        msg["id"],
                        msg["channel_id"],
                        msg["guild_id"],
                        msg["author_name"],
                        msg["author_id"],
                        normalize_content(msg["content"]),
                        msg["timestamp"],
                    ),
                )
                if db.total_changes:
                    inserted += 1
            except Exception as e:
                logger.warning("Failed to insert message %s: %s", msg.get("id"), e)
        await db.commit()
    return inserted


async def store_single_message(
    msg_id: int,
    channel_id: int,
    guild_id: int,
    author_name: str,
    author_id: int,
    content: str,
    timestamp: str,
) -> None:
    """Store a single message (used for live ingestion)."""
    async with aiosqlite.connect(DB_PATH) as db:
        await db.execute(
            """INSERT OR IGNORE INTO messages
               (id, channel_id, guild_id, author_name, author_id, content, timestamp)
               VALUES (?, ?, ?, ?, ?, ?, ?)""",
            (msg_id, channel_id, guild_id, author_name, author_id, normalize_content(content), timestamp),
        )
        await db.commit()


async def store_reactions(
    reactions: list[dict],
) -> int:
    """
    Store emoji reaction data from messages.
    Each dict has: message_id, guild_id, emoji, count, timestamp
    Returns number of reactions stored.
    """
    if not reactions:
        return 0

    async with aiosqlite.connect(DB_PATH) as db:
        await db.executemany(
            """INSERT OR REPLACE INTO emoji_reactions
               (message_id, guild_id, emoji, count, timestamp)
               VALUES (?, ?, ?, ?, ?)""",
            [
                (r["message_id"], r["guild_id"], r["emoji"], r["count"], r["timestamp"])
                for r in reactions
            ],
        )
        await db.commit()
    return len(reactions)


async def get_recent_messages(
    channel_id: int, limit: int = 20
) -> list[dict]:
    """Get the most recent messages from a channel, oldest first."""
    async with aiosqlite.connect(DB_PATH) as db:
        db.row_factory = aiosqlite.Row
        cursor = await db.execute(
            """SELECT author_name, content, timestamp FROM messages
               WHERE channel_id = ?
               ORDER BY timestamp DESC LIMIT ?""",
            (channel_id, limit),
        )
        rows = await cursor.fetchall()
    # Reverse so oldest is first (natural reading order)
    return [dict(r) for r in reversed(rows)]


async def get_random_sample(
    guild_id: int,
    n: int = 300,
    read_channels: Optional[list[int]] = None,
) -> list[dict]:
    """
    Get a random sample of messages from the guild's read-list channels.
    Filters out very short messages (< 5 chars) and bot commands.
    """
    async with aiosqlite.connect(DB_PATH) as db:
        db.row_factory = aiosqlite.Row

        if read_channels:
            placeholders = ",".join("?" for _ in read_channels)
            cursor = await db.execute(
                f"""SELECT author_name, content FROM messages
                    WHERE guild_id = ?
                    AND channel_id IN ({placeholders})
                    AND LENGTH(content) >= 5
                    AND content NOT LIKE '!%'
                    AND content NOT LIKE '/%'
                    ORDER BY RANDOM() LIMIT ?""",
                (guild_id, *read_channels, n),
            )
        else:
            cursor = await db.execute(
                """SELECT author_name, content FROM messages
                   WHERE guild_id = ?
                   AND LENGTH(content) >= 5
                   AND content NOT LIKE '!%'
                   AND content NOT LIKE '/%'
                   ORDER BY RANDOM() LIMIT ?""",
                (guild_id, n),
            )
        rows = await cursor.fetchall()
    return [dict(r) for r in rows]


async def get_message_count(guild_id: int) -> int:
    """Get total message count for a guild."""
    async with aiosqlite.connect(DB_PATH) as db:
        cursor = await db.execute(
            "SELECT COUNT(*) FROM messages WHERE guild_id = ?",
            (guild_id,),
        )
        row = await cursor.fetchone()
    return row[0] if row else 0


# ── Channel Config ───────────────────────────────────────────────────────────


async def add_channel(channel_id: int, guild_id: int, list_type: str) -> bool:
    """Add a channel to the read or chat list. Returns True if added, False if already exists."""
    async with aiosqlite.connect(DB_PATH) as db:
        try:
            await db.execute(
                """INSERT OR IGNORE INTO channel_config (channel_id, guild_id, list_type)
                   VALUES (?, ?, ?)""",
                (channel_id, guild_id, list_type),
            )
            await db.commit()
            return db.total_changes > 0
        except Exception as e:
            logger.error("Failed to add channel %s to %s list: %s", channel_id, list_type, e)
            return False


async def remove_channel(channel_id: int, list_type: str) -> bool:
    """Remove a channel from the read or chat list. Returns True if removed."""
    async with aiosqlite.connect(DB_PATH) as db:
        await db.execute(
            "DELETE FROM channel_config WHERE channel_id = ? AND list_type = ?",
            (channel_id, list_type),
        )
        await db.commit()
        return db.total_changes > 0


async def get_channels(guild_id: int, list_type: str) -> list[int]:
    """Get all channel IDs for a given list type in a guild."""
    async with aiosqlite.connect(DB_PATH) as db:
        cursor = await db.execute(
            "SELECT channel_id FROM channel_config WHERE guild_id = ? AND list_type = ?",
            (guild_id, list_type),
        )
        rows = await cursor.fetchall()
    return [row[0] for row in rows]


async def get_read_channels(guild_id: int) -> list[int]:
    """Get all read-list channel IDs for a guild."""
    return await get_channels(guild_id, "read")


async def get_chat_channels(guild_id: int) -> list[int]:
    """Get all chat-list channel IDs for a guild."""
    return await get_channels(guild_id, "chat")


async def is_read_channel(channel_id: int) -> bool:
    """Check if a channel is on the read list."""
    async with aiosqlite.connect(DB_PATH) as db:
        cursor = await db.execute(
            "SELECT 1 FROM channel_config WHERE channel_id = ? AND list_type = 'read'",
            (channel_id,),
        )
        return await cursor.fetchone() is not None


async def is_chat_channel(channel_id: int) -> bool:
    """Check if a channel is on the chat list."""
    async with aiosqlite.connect(DB_PATH) as db:
        cursor = await db.execute(
            "SELECT 1 FROM channel_config WHERE channel_id = ? AND list_type = 'chat'",
            (channel_id,),
        )
        return await cursor.fetchone() is not None


# ── Analytics ────────────────────────────────────────────────────────────────


async def get_common_emoji(guild_id: int, top_n: int = 20, min_count: int = 2) -> list[tuple[str, int]]:
    """
    Get the most commonly used emoji combining reaction data + text emoji.
    Reactions are weighted more heavily since they reflect true emoji preferences.
    Tries last 3 months first, falls back to all-time if not enough data.
    Returns a list of (emoji, count) tuples sorted by frequency.
    """
    from datetime import datetime, timedelta

    three_months_ago = (datetime.now() - timedelta(days=90)).isoformat()

    # Try recent data first
    results = await _get_combined_emoji(guild_id, three_months_ago, top_n, min_count)

    # Fall back to all-time if not enough
    if len(results) < 5:
        results = await _get_combined_emoji(guild_id, None, top_n, min_count)

    return results


async def _get_combined_emoji(
    guild_id: int, since: str | None, top_n: int, min_count: int
) -> list[tuple[str, int]]:
    """Combine reaction emoji + text emoji into weighted counts."""
    import re

    emoji_counts: dict[str, int] = {}

    async with aiosqlite.connect(DB_PATH) as db:
        # 1. Get reaction counts (these are the most reliable signal)
        if since:
            cursor = await db.execute(
                """SELECT emoji, SUM(count) as total FROM emoji_reactions
                   WHERE guild_id = ? AND timestamp >= ?
                   GROUP BY emoji""",
                (guild_id, since),
            )
        else:
            cursor = await db.execute(
                """SELECT emoji, SUM(count) as total FROM emoji_reactions
                   WHERE guild_id = ?
                   GROUP BY emoji""",
                (guild_id,),
            )
        for emoji, total in await cursor.fetchall():
            # Weight reactions 3x since they're a stronger signal
            emoji_counts[emoji] = emoji_counts.get(emoji, 0) + (total * 3)

        # 2. Also count emoji in message text
        if since:
            cursor = await db.execute(
                "SELECT content FROM messages WHERE guild_id = ? AND timestamp >= ?",
                (guild_id, since),
            )
        else:
            cursor = await db.execute(
                "SELECT content FROM messages WHERE guild_id = ?",
                (guild_id,),
            )
        rows = await cursor.fetchall()

    # Extract text emoji
    unicode_pattern = re.compile(
        "["
        "\U0001F600-\U0001F64F"
        "\U0001F300-\U0001F5FF"
        "\U0001F680-\U0001F6FF"
        "\U0001F900-\U0001F9FF"
        "\U00002600-\U000026FF"
        "\U00002700-\U000027BF"
        "]+",
        flags=re.UNICODE,
    )
    custom_pattern = re.compile(r"<a?:\w+:\d+>")

    for (content,) in rows:
        if not content:
            continue
        for match in unicode_pattern.findall(content):
            for char in match:
                emoji_counts[char] = emoji_counts.get(char, 0) + 1
        for match in custom_pattern.findall(content):
            emoji_counts[match] = emoji_counts.get(match, 0) + 1

    # Filter by minimum count and sort
    sorted_emoji = sorted(
        ((e, c) for e, c in emoji_counts.items() if c >= min_count),
        key=lambda x: x[1],
        reverse=True,
    )
    return sorted_emoji[:top_n]


async def get_avg_message_length(guild_id: int) -> dict:
    """
    Get message length statistics for the guild.
    Returns dict with avg, median, p75, and stddev word counts.
    """
    async with aiosqlite.connect(DB_PATH) as db:
        cursor = await db.execute(
            """SELECT content FROM messages
               WHERE guild_id = ? AND LENGTH(content) >= 5""",
            (guild_id,),
        )
        rows = await cursor.fetchall()

    if not rows:
        return {"avg": 10, "median": 8, "p75": 15, "stddev": 5}

    lengths = sorted(len(content.split()) for (content,) in rows if content)

    n = len(lengths)
    avg = sum(lengths) / n
    median = lengths[n // 2]
    p75 = lengths[int(n * 0.75)]

    # Calculate standard deviation
    variance = sum((l - avg) ** 2 for l in lengths) / n
    stddev = variance ** 0.5

    return {"avg": round(avg, 1), "median": median, "p75": p75, "stddev": round(stddev, 1)}


async def get_active_hours(guild_id: int) -> list[int]:
    """
    Get the hours (0-23) when the server is most active.
    Returns a list of hours sorted by activity, most active first.
    """
    async with aiosqlite.connect(DB_PATH) as db:
        cursor = await db.execute(
            """SELECT timestamp FROM messages WHERE guild_id = ?""",
            (guild_id,),
        )
        rows = await cursor.fetchall()

    if not rows:
        # Default: 9am to 11pm
        return list(range(9, 24))

    from datetime import datetime as dt
    hour_counts: dict[int, int] = {}
    for (ts,) in rows:
        try:
            hour = dt.fromisoformat(ts).hour
            hour_counts[hour] = hour_counts.get(hour, 0) + 1
        except (ValueError, TypeError):
            continue

    if not hour_counts:
        return list(range(9, 24))

    # Return hours that have at least 10% of the peak hour's activity
    peak = max(hour_counts.values())
    threshold = peak * 0.10
    active = [h for h, c in hour_counts.items() if c >= threshold]
    active.sort()

    return active if active else list(range(9, 24))

