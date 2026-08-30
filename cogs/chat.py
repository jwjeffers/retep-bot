from __future__ import annotations
"""Chat cog — handles @mentions, /ask, and /teams commands."""

import logging
import random
import discord
from discord.ext import commands
from discord import app_commands
from core import database
from core.markov import get_chain

logger = logging.getLogger(__name__)

LOL_ROLES = ["Top", "Jungle", "Mid", "Bot", "Support"]


def strip_trailing_period(text: str) -> str:
    """Remove trailing period from Markov output to look natural."""
    if text.endswith(".") and not text.endswith(".."):
        return text[:-1]
    return text


class ChatCog(commands.Cog):
    """Responds when Retep is @mentioned or asked via /ask."""

    def __init__(self, bot: commands.Bot):
        self.bot = bot

    @commands.Cog.listener()
    async def on_message(self, message: discord.Message):
        """Listen for @mentions in chat-list channels."""
        # Ignore own messages
        if message.author == self.bot.user:
            return

        # Ignore DMs
        if not message.guild:
            return

        # Only respond if the bot is mentioned
        if self.bot.user not in message.mentions:
            return

        # Only respond in chat-list channels
        if not await database.is_chat_channel(message.channel.id):
            return

        logger.info(
            "Mentioned by %s in #%s: %s",
            message.author.name,
            message.channel.name,
            message.content[:100],
        )

        # Clean the mention from the message to use as seed
        clean_content = message.content.replace(f"<@{self.bot.user.id}>", "").strip()

        # Generate response using Markov chain
        chain = await get_chain(message.guild.id)
        if chain.is_built:
            response = chain.generate(
                max_words=25,
                seed_text=clean_content if clean_content else None,
            )
            response = strip_trailing_period(response)  # #2
        else:
            response = ""

        if response:
            # Just reply directly — the original message is already visible
            await message.reply(response, mention_author=False)
        else:
            logger.warning("Empty Markov response for mention in #%s", message.channel.name)

    @app_commands.command(name="ask", description="Ask Retep a question")
    @app_commands.describe(question="What do you want to ask Retep?")
    async def ask_command(
        self, interaction: discord.Interaction, question: str
    ):
        """Slash command to ask Retep something."""
        # Defer IMMEDIATELY to avoid 3-second interaction timeout
        await interaction.response.defer()

        # Only in chat-list channels
        if not await database.is_chat_channel(interaction.channel_id):
            await interaction.followup.send(
                "I'm not allowed to chat in this channel! An admin needs to add it with `/chatlist add`.",
                ephemeral=True,
            )
            return

        # Generate response using Markov chain
        chain = await get_chain(interaction.guild_id)
        if chain.is_built:
            response = chain.generate(
                max_words=25,
                seed_text=question,
            )
            response = strip_trailing_period(response)  # #2
        else:
            response = "need to /sync first so i have something to work with"

        # Show the question and response together
        await interaction.followup.send(
            f"**{interaction.user.display_name} asked:** {question}\n\n{response}"
        )

    # ── /teams — League of Legends custom game team maker ────────────────

    @app_commands.command(
        name="teams",
        description="Split players into two 5v5 League teams with random roles",
    )
    @app_commands.describe(
        players="Comma-separated player names (e.g. Alice, Bob, Charlie, ...)"
    )
    async def teams_command(
        self, interaction: discord.Interaction, players: str
    ):
        """Generate two random League of Legends teams with roles."""
        await interaction.response.defer()

        # Parse player names
        names = [n.strip() for n in players.split(",") if n.strip()]

        if len(names) < 2:
            await interaction.followup.send(
                "Need at least 2 players! Separate names with commas.\n"
                "Example: `/teams Alice, Bob, Charlie, Dave, Eve`",
                ephemeral=True,
            )
            return

        if len(names) > 10:
            await interaction.followup.send(
                f"Too many players ({len(names)})! Max is 10 for a 5v5.",
                ephemeral=True,
            )
            return

        if len(names) % 2 != 0:
            await interaction.followup.send(
                f"Need an even number of players for fair teams! Got {len(names)}.",
                ephemeral=True,
            )
            return

        team_size = len(names) // 2

        # Shuffle and split into two teams
        random.shuffle(names)
        team1_players = names[:team_size]
        team2_players = names[team_size:]

        # Assign roles (use as many as needed, up to 5)
        roles = LOL_ROLES[:team_size]
        random.shuffle(roles)
        team1_roles = list(roles)
        random.shuffle(roles)
        team2_roles = list(roles)

        # Generate team names from Markov chain
        team1_name, team2_name = await self._generate_team_names(interaction.guild_id)

        # Build the embed
        embed = discord.Embed(
            title="⚔️ CUSTOM GAME TEAMS ⚔️",
            color=discord.Color.gold(),
        )

        # Team 1
        team1_lines = []
        for i, player in enumerate(team1_players):
            role = team1_roles[i]
            emoji = _role_emoji(role)
            team1_lines.append(f"{emoji} **{role}:** {player}")
        embed.add_field(
            name=f"🔵 {team1_name}",
            value="\n".join(team1_lines),
            inline=True,
        )

        # Team 2
        team2_lines = []
        for i, player in enumerate(team2_players):
            role = team2_roles[i]
            emoji = _role_emoji(role)
            team2_lines.append(f"{emoji} **{role}:** {player}")
        embed.add_field(
            name=f"🔴 {team2_name}",
            value="\n".join(team2_lines),
            inline=True,
        )

        embed.set_footer(text="GL HF 🎮")

        await interaction.followup.send(embed=embed)
        logger.info(
            "Generated teams: %s vs %s (%d players)",
            team1_name, team2_name, len(names),
        )

    async def _generate_team_names(self, guild_id: int) -> tuple[str, str]:
        """Generate two unique team names using the Markov chain."""
        chain = await get_chain(guild_id)
        names = set()

        if chain.is_built:
            # Generate short Markov phrases as team names
            for _ in range(20):  # Try up to 20 times
                name = chain.generate(max_words=4)
                name = strip_trailing_period(name)
                # Clean it up — keep it short and punchy
                words = name.split()[:3]  # Max 3 words
                if words:
                    clean = " ".join(words).title()
                    names.add(clean)
                if len(names) >= 2:
                    break

        # Fallback names if Markov doesn't produce enough
        fallbacks = [
            "Team Diff", "GG Go Next", "FF 15", "Dragon Slayers",
            "Baron Bashers", "Rift Walkers", "Turret Divers",
            "Flash On D", "Flash On F", "Jungle Diff",
        ]

        while len(names) < 2:
            names.add(random.choice(fallbacks))

        result = list(names)[:2]
        return result[0], result[1]


def _role_emoji(role: str) -> str:
    """Get an emoji for a League role."""
    return {
        "Top": "🛡️",
        "Jungle": "🌿",
        "Mid": "⚡",
        "Bot": "🏹",
        "Support": "💚",
    }.get(role, "🎮")


async def setup(bot: commands.Bot):
    await bot.add_cog(ChatCog(bot))

