"""Sync cog — chat history ingestion from Discord channels."""

import logging
from datetime import time
import discord
from discord.ext import commands, tasks
from discord import app_commands
from core import database
from core.config import Config

logger = logging.getLogger(__name__)

# Midnight sync time
MIDNIGHT = time(hour=0, minute=0, second=0)


class SyncCog(commands.Cog):
    """Handles chat history ingestion from read-list channels."""

    def __init__(self, bot: commands.Bot):
        self.bot = bot
        self._syncing = False

    async def cog_load(self):
        """Start the midnight sync loop when cog loads."""
        self.midnight_sync_loop.start()

    async def cog_unload(self):
        """Stop the midnight sync loop when cog unloads."""
        self.midnight_sync_loop.cancel()

    @commands.Cog.listener()
    async def on_ready(self):
        """Auto-sync recent messages on startup."""
        logger.info("Starting auto-sync of recent messages...")
        for guild in self.bot.guilds:
            read_channels = await database.get_read_channels(guild.id)
            if not read_channels:
                logger.info("No read-list channels for guild %s -- skipping auto-sync", guild.name)
                continue

            total = 0
            for channel_id in read_channels:
                channel = self.bot.get_channel(channel_id)
                if channel and isinstance(channel, discord.TextChannel):
                    count = await self._sync_channel(channel, limit=1000)
                    total += count

            logger.info("Auto-synced %d messages for guild %s", total, guild.name)

    @tasks.loop(time=MIDNIGHT)
    async def midnight_sync_loop(self):
        """Full sync every night at midnight."""
        logger.info("Midnight sync starting...")

        for guild in self.bot.guilds:
            read_channels = await database.get_read_channels(guild.id)
            if not read_channels:
                continue

            if self._syncing:
                logger.warning("Skipping midnight sync -- another sync is in progress")
                return

            self._syncing = True
            total = 0

            for channel_id in read_channels:
                channel = self.bot.get_channel(channel_id)
                if channel and isinstance(channel, discord.TextChannel):
                    try:
                        count = await self._sync_channel(channel, limit=Config.HISTORY_DEPTH)
                        total += count
                    except Exception as e:
                        logger.error("Midnight sync error for #%s: %s", channel.name, e)

            # Rebuild Markov chain with new data
            from core.markov import get_chain
            chain = await get_chain(guild.id, force_rebuild=True)

            total_stored = await database.get_message_count(guild.id)
            logger.info(
                "Midnight sync complete for %s: %d new messages, %d total, "
                "Markov: %d messages / %d states",
                guild.name, total, total_stored,
                chain.message_count, len(chain.chain),
            )

            self._syncing = False

    @midnight_sync_loop.before_loop
    async def before_midnight_sync(self):
        """Wait until the bot is ready before starting the loop."""
        await self.bot.wait_until_ready()

    @commands.Cog.listener()
    async def on_message(self, message: discord.Message):
        """Live ingestion — store new messages from read-list channels."""
        # Ignore bot's own messages
        if message.author == self.bot.user:
            return

        # Ignore DMs
        if not message.guild:
            return

        # Ignore empty messages (images only, embeds, etc.)
        if not message.content:
            return

        # Only ingest from read-list channels
        if not await database.is_read_channel(message.channel.id):
            return

        await database.store_single_message(
            msg_id=message.id,
            channel_id=message.channel.id,
            guild_id=message.guild.id,
            author_name=message.author.display_name,
            author_id=message.author.id,
            content=message.content,
            timestamp=message.created_at.isoformat(),
        )

    @app_commands.command(
        name="sync",
        description="Sync chat history from read-list channels (admin only)",
    )
    @app_commands.default_permissions(manage_guild=True)
    async def sync_command(self, interaction: discord.Interaction):
        """Manually trigger a full history sync."""
        if self._syncing:
            await interaction.response.send_message(
                "A sync is already in progress!", ephemeral=True
            )
            return

        read_channels = await database.get_read_channels(interaction.guild_id)
        if not read_channels:
            await interaction.response.send_message(
                "No read-list channels configured! Use `/readlist add #channel` first.",
                ephemeral=True,
            )
            return

        self._syncing = True
        await interaction.response.send_message(
            f"Starting full sync of {len(read_channels)} channel(s)... "
            f"This may take a while (up to {Config.HISTORY_DEPTH:,} messages per channel)."
        )

        total_messages = 0
        for channel_id in read_channels:
            channel = self.bot.get_channel(channel_id)
            if channel is None or not isinstance(channel, discord.TextChannel):
                continue

            try:
                count = await self._sync_channel(channel, limit=Config.HISTORY_DEPTH)
                total_messages += count
                await interaction.followup.send(
                    f"#{channel.name}: synced {count:,} messages"
                )
            except Exception as e:
                logger.error("Error syncing #%s: %s", channel.name, e)
                await interaction.followup.send(
                    f"#{channel.name}: error -- {str(e)[:100]}"
                )

        self._syncing = False

        # Rebuild Markov chain with new data
        from core.markov import get_chain
        chain = await get_chain(interaction.guild_id, force_rebuild=True)

        total_stored = await database.get_message_count(interaction.guild_id)
        await interaction.followup.send(
            f"Sync complete! Added {total_messages:,} messages. "
            f"Total in database: {total_stored:,}\n"
            f"Markov chain rebuilt: {chain.message_count:,} messages learned, "
            f"{len(chain.chain):,} unique word patterns"
        )

    async def _sync_channel(
        self, channel: discord.TextChannel, limit: int = 1000
    ) -> int:
        """
        Fetch message history from a channel and store in the database.
        Also collects emoji reaction data.
        Returns the number of new messages stored.
        """
        messages_to_store = []
        reactions_to_store = []
        count = 0

        try:
            async for message in channel.history(limit=limit, oldest_first=True):
                # Skip bot messages and empty messages
                if message.author.bot or not message.content:
                    continue

                messages_to_store.append({
                    "id": message.id,
                    "channel_id": channel.id,
                    "guild_id": channel.guild.id,
                    "author_name": message.author.display_name,
                    "author_id": message.author.id,
                    "content": message.content,
                    "timestamp": message.created_at.isoformat(),
                })

                # Collect reaction data
                for reaction in message.reactions:
                    emoji_str = str(reaction.emoji)
                    # For custom emoji, use the Discord format
                    if hasattr(reaction.emoji, 'id') and reaction.emoji.id:
                        if reaction.emoji.animated:
                            emoji_str = f"<a:{reaction.emoji.name}:{reaction.emoji.id}>"
                        else:
                            emoji_str = f"<:{reaction.emoji.name}:{reaction.emoji.id}>"
                    reactions_to_store.append({
                        "message_id": message.id,
                        "guild_id": channel.guild.id,
                        "emoji": emoji_str,
                        "count": reaction.count,
                        "timestamp": message.created_at.isoformat(),
                    })

                # Batch insert every 500 messages
                if len(messages_to_store) >= 500:
                    await database.store_messages(messages_to_store)
                    count += len(messages_to_store)
                    messages_to_store.clear()

                # Batch insert reactions every 500
                if len(reactions_to_store) >= 500:
                    await database.store_reactions(reactions_to_store)
                    reactions_to_store.clear()

        except discord.Forbidden:
            logger.warning("No permission to read #%s", channel.name)
        except Exception as e:
            logger.error("Error reading #%s history: %s", channel.name, e)

        # Store remaining messages
        if messages_to_store:
            await database.store_messages(messages_to_store)
            count += len(messages_to_store)

        # Store remaining reactions
        if reactions_to_store:
            reaction_count = await database.store_reactions(reactions_to_store)
            logger.info("Synced %d reactions from #%s", reaction_count, channel.name)

        logger.info("Synced %d messages from #%s", count, channel.name)
        return count


async def setup(bot: commands.Bot):
    await bot.add_cog(SyncCog(bot))
