"""Random talk cog — sends unprompted messages and emoji reactions."""

import logging
import random
from datetime import datetime, timedelta, timezone
import discord
from discord.ext import commands, tasks
from core import database
from core.markov import get_chain
from core.config import Config
from core.scheduler import DailySchedule

logger = logging.getLogger(__name__)


def strip_trailing_period(text: str) -> str:
    """Remove trailing period from Markov output to look natural."""
    if text.endswith(".") and not text.endswith(".."):
        return text[:-1]
    return text


class RandomTalkCog(commands.Cog):
    """Sends unprompted Markov-generated messages and emoji reactions."""

    def __init__(self, bot: commands.Bot):
        self.bot = bot
        self.schedule = DailySchedule()
        self._emoji_pool: list[str] = []
        self._emoji_weights: list[int] = []
        self._active_hours: list[int] | None = None
        self._length_avg: float = 10.0
        self._length_stddev: float = 5.0

    def _sample_max_words(self) -> int:
        """Sample a max_words value from a bell curve based on server's message length stats."""
        sampled = random.gauss(self._length_avg, self._length_stddev)
        # Clamp to reasonable range
        return max(3, min(50, round(sampled)))

    async def cog_load(self):
        """Called when the cog is loaded — start background loops."""
        self.schedule_check_loop.start()

    async def cog_unload(self):
        """Called when the cog is unloaded — stop loops."""
        self.schedule_check_loop.cancel()

    async def _load_server_stats(self, guild_id: int):
        """Load emoji, active hours, and message length stats from the database."""
        # Load common emoji for reactions (#5) — now with frequency weights
        emoji_data = await database.get_common_emoji(guild_id, top_n=15)
        if emoji_data:
            self._emoji_pool = [e for e, _ in emoji_data]
            self._emoji_weights = [c for _, c in emoji_data]
            logger.info("Loaded %d common emoji for weighted reactions", len(self._emoji_pool))

        # Load active hours (#8)
        self._active_hours = await database.get_active_hours(guild_id)
        logger.info("Active hours: %s", self._active_hours)

        # Load message length stats (#6)
        stats = await database.get_avg_message_length(guild_id)
        self._length_avg = stats["avg"]
        self._length_stddev = stats["stddev"]
        logger.info("Message length stats: avg=%.1f, median=%d, p75=%d, stddev=%.1f",
                     stats["avg"], stats["median"], stats["p75"], stats["stddev"])

    @tasks.loop(minutes=5)
    async def schedule_check_loop(self):
        """Check every 5 minutes if a scheduled message is due."""
        now = datetime.now()

        # Regenerate schedule if it's a new day or doesn't exist
        if self.schedule.is_stale(now):
            # Load stats on first run or new day
            for guild in self.bot.guilds:
                await self._load_server_stats(guild.id)

            self.schedule.generate(now, active_hours=self._active_hours)
            logger.info("New daily schedule:\n%s", self.schedule.status_summary())

        # Check if any message is due
        due_index = self.schedule.check_due(now)
        if due_index is None:
            return

        logger.info("Scheduled message #%d is due!", due_index)

        # Find a suitable chat-list channel with recent activity
        channel = await self._pick_active_channel()
        if channel is None:
            logger.info("No active chat channels -- skipping scheduled message")
            self.schedule.mark_sent(due_index)
            return

        # Generate and send the message
        try:
            chain = await get_chain(channel.guild.id)
            if chain.is_built:
                message_text = chain.generate(max_words=self._sample_max_words())
                message_text = strip_trailing_period(message_text)  # #2
            else:
                message_text = ""

            if message_text:
                # #9: Sometimes reply to the last message instead of standalone
                sent_msg = await self._send_or_reply(channel, message_text)
                logger.info(
                    "Sent scheduled message in #%s: %s",
                    channel.name,
                    message_text[:80],
                )
            else:
                logger.warning("Empty Markov message -- skipping")
        except Exception as e:
            logger.error("Failed to send scheduled message: %s", e)

        self.schedule.mark_sent(due_index)

    @schedule_check_loop.before_loop
    async def before_schedule_check(self):
        """Wait until the bot is ready before starting the loop."""
        await self.bot.wait_until_ready()

    # ── #5: Emoji Reactions ──────────────────────────────────────────────

    @commands.Cog.listener()
    async def on_message(self, message: discord.Message):
        """Occasionally react to messages with common server emoji."""
        # Ignore own messages and bots
        if message.author == self.bot.user or message.author.bot:
            return
        if not message.guild:
            return

        # Only react in chat-list channels
        if not await database.is_chat_channel(message.channel.id):
            return

        # ~8% chance to react to any message
        if random.random() > 0.08:
            return

        if not self._emoji_pool:
            # Try to load if not loaded yet
            await self._load_server_stats(message.guild.id)

        if not self._emoji_pool:
            return

        # Pick emoji weighted by server usage frequency
        emoji = random.choices(self._emoji_pool, weights=self._emoji_weights, k=1)[0]

        try:
            await message.add_reaction(emoji)
        except (discord.HTTPException, discord.NotFound):
            # Emoji might not be available — ignore
            pass

    # ── #9: Reply Threading ──────────────────────────────────────────────

    async def _send_or_reply(self, channel: discord.TextChannel, text: str) -> discord.Message:
        """
        Send a message, sometimes as a reply to the most recent message.
        ~40% chance to reply to the last message, 60% chance standalone.
        """
        if random.random() < 0.4:
            try:
                # Get the most recent message
                async for last_msg in channel.history(limit=1):
                    if last_msg.author != self.bot.user:
                        return await last_msg.reply(text, mention_author=False)
                    break
            except (discord.HTTPException, discord.Forbidden):
                pass

        # Standalone message
        return await channel.send(text)

    async def _pick_active_channel(self) -> discord.TextChannel | None:
        """
        Pick a random chat-list channel that has had activity in the last 2 hours.
        Returns None if no channels qualify.
        """
        active_channels = []

        for guild in self.bot.guilds:
            chat_channel_ids = await database.get_chat_channels(guild.id)

            for channel_id in chat_channel_ids:
                channel = self.bot.get_channel(channel_id)
                if channel is None or not isinstance(channel, discord.TextChannel):
                    continue

                # Check if there's been recent activity
                try:
                    async for msg in channel.history(limit=1):
                        # Use offset-aware comparison
                        msg_age = datetime.now(timezone.utc) - msg.created_at.replace(
                            tzinfo=timezone.utc
                        )
                        if msg_age < timedelta(hours=2):
                            active_channels.append(channel)
                        break
                except (discord.Forbidden, discord.HTTPException):
                    continue

        if not active_channels:
            return None

        return random.choice(active_channels)

    def get_status(self) -> str:
        """Get the current schedule status for the /retep status command."""
        return self.schedule.status_summary()


async def setup(bot: commands.Bot):
    await bot.add_cog(RandomTalkCog(bot))
