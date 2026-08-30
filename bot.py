from __future__ import annotations
"""
Retep — Discord Chat-Personality Bot
Entry point: loads config, initializes database, registers cogs, and starts the bot.
"""

import asyncio
import logging
import sys
import discord
from discord.ext import commands
from core.config import Config
from core import database

# ── Logging Setup ────────────────────────────────────────────────────────────

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S",
    handlers=[
        logging.StreamHandler(sys.stdout),
        logging.FileHandler("retep.log", encoding="utf-8"),
    ],
)
logger = logging.getLogger("retep")

# Suppress noisy discord.py logs
logging.getLogger("discord").setLevel(logging.WARNING)
logging.getLogger("discord.http").setLevel(logging.WARNING)

# ── Bot Setup ────────────────────────────────────────────────────────────────

# Intents we need
intents = discord.Intents.default()
intents.message_content = True  # Required for reading message content
intents.messages = True
intents.guilds = True

bot = commands.Bot(
    command_prefix="!",  # Not really used (we use slash commands), but required
    intents=intents,
    help_command=None,  # Disable default help
)

# List of cogs to load
COGS = [
    "cogs.chat",
    "cogs.random_talk",
    "cogs.sync",
    "cogs.admin",
]


@bot.event
async def on_ready():
    """Called when the bot is connected and ready."""
    logger.info("=" * 50)
    logger.info("  %s is online!", Config.BOT_NAME)
    logger.info("  Logged in as: %s (ID: %s)", bot.user.name, bot.user.id)
    logger.info("  Servers: %s", ", ".join(g.name for g in bot.guilds))
    logger.info("=" * 50)

    # Sync slash commands with Discord
    try:
        synced = await bot.tree.sync()
        logger.info("Synced %d slash command(s)", len(synced))
    except Exception as e:
        logger.error("Failed to sync slash commands: %s", e)


async def main():
    """Main entry point."""
    # Validate config
    errors = Config.validate()
    if errors:
        for err in errors:
            logger.error("Config error: %s", err)
        logger.error("Fix the above errors in your .env file and try again.")
        sys.exit(1)

    # Initialize database
    await database.init_db(Config.DB_PATH)

    # Load cogs
    async with bot:
        for cog in COGS:
            try:
                await bot.load_extension(cog)
                logger.info("Loaded cog: %s", cog)
            except Exception as e:
                logger.error("Failed to load cog %s: %s", cog, e)

        # Start the bot
        logger.info("Starting %s...", Config.BOT_NAME)
        await bot.start(Config.DISCORD_TOKEN)


if __name__ == "__main__":
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        logger.info("Shutting down %s...", Config.BOT_NAME)
