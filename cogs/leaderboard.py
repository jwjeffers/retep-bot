from __future__ import annotations
"""Leaderboard cog — tracks the best message scores and keeps a live top 10 embed."""

import asyncio
import logging
from datetime import datetime, timezone
import discord
from discord.ext import commands
from discord import app_commands
from core import database

logger = logging.getLogger(__name__)

LEADERBOARD_SIZE = 10
MEDALS = ["🥇", "🥈", "🥉"]


class LeaderboardCog(commands.Cog):
    """Keeps a live top 10 leaderboard of each user's best message score."""

    def __init__(self, bot: commands.Bot):
        self.bot = bot
        # One lock per guild so concurrent scores don't post duplicate boards
        self._locks: dict[int, asyncio.Lock] = {}

    leaderboard_group = app_commands.Group(
        name="leaderboard",
        description="Retep's message score leaderboard",
    )

    @leaderboard_group.command(name="channel", description="Set the channel where the leaderboard is posted")
    @app_commands.describe(channel="The channel the leaderboard should live in")
    async def leaderboard_channel(
        self, interaction: discord.Interaction, channel: discord.TextChannel
    ):
        await interaction.response.defer(ephemeral=True)
        # Discord only supports default permissions on top-level commands, so check here
        if not interaction.user.guild_permissions.manage_guild:
            await interaction.followup.send(
                "You need the **Manage Server** permission to set the leaderboard channel.",
            )
            return
        await database.set_leaderboard_channel(interaction.guild_id, channel.id)
        posted = await self.refresh(interaction.guild_id)
        if posted:
            await interaction.followup.send(
                f"🏆 The leaderboard now lives in {channel.mention}.",
            )
        else:
            await interaction.followup.send(
                f"Saved {channel.mention}, but I couldn't post there. "
                f"Check that I can send messages and embed links in that channel.",
            )

    @leaderboard_group.command(name="show", description="Show the top 10 message scores")
    async def leaderboard_show(self, interaction: discord.Interaction):
        await interaction.response.defer(ephemeral=True)
        embed = await self.build_embed(interaction.guild_id)
        await interaction.followup.send(embed=embed)

    async def build_embed(self, guild_id: int) -> discord.Embed:
        """Build the top 10 leaderboard embed for a guild."""
        top = await database.get_top_scores(guild_id, LEADERBOARD_SIZE)

        lines = []
        for rank, entry in enumerate(top, start=1):
            badge = MEDALS[rank - 1] if rank <= len(MEDALS) else f"`{rank}.`"
            lines.append(f"{badge} <@{entry['user_id']}> — **{entry['score']:.2f}**")

        embed = discord.Embed(
            title="🏆 Retep Leaderboard 🏆",
            description="\n".join(lines) or "No scores yet — ask Retep something!",
            color=discord.Color.gold(),
            timestamp=datetime.now(timezone.utc),
        )
        embed.set_footer(text="Best message score per user • Last updated")
        return embed

    async def refresh(self, guild_id: int) -> bool:
        """
        Edit the live leaderboard message, or post a new one if it's missing.
        Returns True if the leaderboard is up to date in its channel.
        """
        lock = self._locks.setdefault(guild_id, asyncio.Lock())
        async with lock:
            config = await database.get_leaderboard_config(guild_id)
            if not config:
                return False

            channel = self.bot.get_channel(config["channel_id"])
            if channel is None:
                logger.warning("Leaderboard channel %s not found", config["channel_id"])
                return False

            embed = await self.build_embed(guild_id)

            try:
                if config["message_id"]:
                    try:
                        message = await channel.fetch_message(config["message_id"])
                        await message.edit(embed=embed)
                        return True
                    except discord.NotFound:
                        logger.info("Leaderboard message was deleted, posting a new one")

                message = await channel.send(embed=embed)
                await database.set_leaderboard_message(guild_id, message.id)
                return True
            except discord.HTTPException as e:
                logger.error("Failed to update leaderboard in #%s: %s", channel, e)
                return False

    async def on_new_score(self, guild_id: int, user_id: int, score: float) -> None:
        """Refresh the leaderboard if a just-recorded score made the top 10."""
        top = await database.get_top_scores(guild_id, LEADERBOARD_SIZE)
        if any(e["user_id"] == user_id and e["score"] == score for e in top):
            await self.refresh(guild_id)


async def setup(bot: commands.Bot):
    await bot.add_cog(LeaderboardCog(bot))
