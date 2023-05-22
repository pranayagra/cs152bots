import discord
from discord.utils import get
from discord.ext import commands

DEBUG = True

def is_debug():
    return DEBUG

async def check_issue(condition, func, message):
    if condition: 
        await func(message)
        return True
    return False

def get_category_by_name(guild, category_name):
    for category in guild.categories:
        if category.name == category_name:
            return category
    return None

def get_channel(guild, channel_name):
    return discord.utils.get(guild.channels, name=channel_name)

async def delete_channel(guild, channel_name):
    channel = get_channel(guild, channel_name)
    if channel:
        await channel.delete()
        return True
    else:
        return False

# does not work right now
# def check_DM(m):
    # return m.author == user2 and isinstance(m.channel, discord.DMChannel)

