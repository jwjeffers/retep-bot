"""Admin cog — channel list management and bot status."""

import logging
import discord
from discord.ext import commands
from discord import app_commands
from core import database

logger = logging.getLogger(__name__)


class AdminCog(commands.Cog):
    """Admin commands for managing read/chat channel lists and bot status."""

    def __init__(self, bot: commands.Bot):
        self.bot = bot

    # ── Read List Commands ──────────────────────────────────────────────

    readlist_group = app_commands.Group(
        name="readlist",
        description="Manage channels Retep reads from to learn personality",
        default_permissions=discord.Permissions(manage_guild=True),
    )

    @readlist_group.command(name="add", description="Add a channel to Retep's read list")
    @app_commands.describe(channel="The channel Retep should read from")
    async def readlist_add(
        self, interaction: discord.Interaction, channel: discord.TextChannel
    ):
        await interaction.response.defer(ephemeral=True)
        added = await database.add_channel(channel.id, interaction.guild_id, "read")
        if added:
            await interaction.followup.send(
                f"✅ Added {channel.mention} to the **read list**. "
                f"Run `/sync` to fetch its history.",
            )
        else:
            await interaction.followup.send(
                f"{channel.mention} is already on the read list.",
            )

    @readlist_group.command(name="remove", description="Remove a channel from Retep's read list")
    @app_commands.describe(channel="The channel to remove")
    async def readlist_remove(
        self, interaction: discord.Interaction, channel: discord.TextChannel
    ):
        await interaction.response.defer(ephemeral=True)
        removed = await database.remove_channel(channel.id, "read")
        if removed:
            await interaction.followup.send(
                f"✅ Removed {channel.mention} from the **read list**.",
            )
        else:
            await interaction.followup.send(
                f"{channel.mention} wasn't on the read list.",
            )

    @readlist_group.command(name="show", description="Show all channels on Retep's read list")
    async def readlist_show(self, interaction: discord.Interaction):
        await interaction.response.defer(ephemeral=True)
        channels = await database.get_read_channels(interaction.guild_id)
        if not channels:
            await interaction.followup.send(
                "📭 No channels on the read list yet. Use `/readlist add #channel` to add one.",
            )
            return

        channel_mentions = []
        for ch_id in channels:
            ch = self.bot.get_channel(ch_id)
            channel_mentions.append(ch.mention if ch else f"(deleted: {ch_id})")

        await interaction.followup.send(
            "📖 **Read List** (channels Retep learns from):\n"
            + "\n".join(f"  • {m}" for m in channel_mentions),
        )

    # ── Chat List Commands ──────────────────────────────────────────────

    chatlist_group = app_commands.Group(
        name="chatlist",
        description="Manage channels where Retep can speak",
        default_permissions=discord.Permissions(manage_guild=True),
    )

    @chatlist_group.command(name="add", description="Add a channel where Retep can chat")
    @app_commands.describe(channel="The channel Retep can speak in")
    async def chatlist_add(
        self, interaction: discord.Interaction, channel: discord.TextChannel
    ):
        await interaction.response.defer(ephemeral=True)
        added = await database.add_channel(channel.id, interaction.guild_id, "chat")
        if added:
            await interaction.followup.send(
                f"✅ Added {channel.mention} to the **chat list**. "
                f"Retep can now speak there!",
            )
        else:
            await interaction.followup.send(
                f"{channel.mention} is already on the chat list.",
            )

    @chatlist_group.command(name="remove", description="Remove a channel from Retep's chat list")
    @app_commands.describe(channel="The channel to remove")
    async def chatlist_remove(
        self, interaction: discord.Interaction, channel: discord.TextChannel
    ):
        await interaction.response.defer(ephemeral=True)
        removed = await database.remove_channel(channel.id, "chat")
        if removed:
            await interaction.followup.send(
                f"✅ Removed {channel.mention} from the **chat list**.",
            )
        else:
            await interaction.followup.send(
                f"{channel.mention} wasn't on the chat list.",
            )

    @chatlist_group.command(name="show", description="Show all channels where Retep can speak")
    async def chatlist_show(self, interaction: discord.Interaction):
        await interaction.response.defer(ephemeral=True)
        channels = await database.get_chat_channels(interaction.guild_id)
        if not channels:
            await interaction.followup.send(
                "📭 No channels on the chat list yet. Use `/chatlist add #channel` to add one.",
            )
            return

        channel_mentions = []
        for ch_id in channels:
            ch = self.bot.get_channel(ch_id)
            channel_mentions.append(ch.mention if ch else f"(deleted: {ch_id})")

        await interaction.followup.send(
            "💬 **Chat List** (channels Retep can speak in):\n"
            + "\n".join(f"  • {m}" for m in channel_mentions),
        )

    # ── Status Command ──────────────────────────────────────────────────

    @app_commands.command(name="retep", description="Show Retep's status")
    @app_commands.default_permissions(manage_guild=True)
    async def retep_status(self, interaction: discord.Interaction):
        """Show bot status: channels, schedule, message count."""
        await interaction.response.defer(ephemeral=True)

        read_channels = await database.get_read_channels(interaction.guild_id)
        chat_channels = await database.get_chat_channels(interaction.guild_id)
        msg_count = await database.get_message_count(interaction.guild_id)

        # Get schedule from RandomTalkCog
        random_talk = self.bot.get_cog("RandomTalkCog")
        schedule_status = (
            random_talk.get_status() if random_talk else "Schedule unavailable"
        )

        read_list = ", ".join(
            (self.bot.get_channel(c).mention if self.bot.get_channel(c) else str(c))
            for c in read_channels
        ) or "None"

        chat_list = ", ".join(
            (self.bot.get_channel(c).mention if self.bot.get_channel(c) else str(c))
            for c in chat_channels
        ) or "None"

        embed = discord.Embed(
            title="🤖 Retep Status",
            color=discord.Color.blurple(),
        )
        embed.add_field(name="📖 Read Channels", value=read_list, inline=False)
        embed.add_field(name="💬 Chat Channels", value=chat_list, inline=False)
        embed.add_field(name="📊 Messages Stored", value=f"{msg_count:,}", inline=True)
        embed.add_field(
            name="📅 Today's Schedule", value=schedule_status, inline=False
        )

        await interaction.followup.send(embed=embed)


async def setup(bot: commands.Bot):
    await bot.add_cog(AdminCog(bot))
