"""Minimal bot: no privileged intents and no message-content access required."""
import logging
import os

import discord

logging.basicConfig(level=logging.INFO)
bot = discord.Client(intents=discord.Intents.default())


@bot.event
async def on_ready():
    logging.info("Připojeno k Discordu jako %s", bot.user)


bot.run(os.environ["DISCORD_TOKEN"])

