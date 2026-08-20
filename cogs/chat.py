"""Chat cog — handles @mentions and /ask command using Markov chain."""

import logging
import discord
from discord.ext import commands
from discord import app_commands
from core import database
from core.markov import get_chain

logger = logging.getLogger(__name__)


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
            if clean_content:
                # #9: Reply to the mention message directly
                await message.reply(
                    f"**{message.author.display_name} asked:** {clean_content}\n\n{response}",
                    mention_author=False,
                )
            else:
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


async def setup(bot: commands.Bot):
    await bot.add_cog(ChatCog(bot))
