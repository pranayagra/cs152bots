import discord
from discord.utils import get
from discord.ext import commands
from enum import Enum, auto

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

class BadUserState(Enum):
    SUSPEND = auto()
    WARN = auto()
    NONE = auto()
