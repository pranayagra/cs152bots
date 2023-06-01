import discord
from discord.utils import get
from discord.ext import commands
from enum import Enum, auto
import openai
import os
import json

token_path = 'tokens.json'
if not os.path.isfile(token_path):
    raise Exception(f"{token_path} not found!")
with open(token_path) as f:
    # If you get an error here, it means your token is formatted incorrectly. Did you put it in quotes?
    tokens = json.load(f)
    discord_token = tokens['discord']
    openai.organization = tokens['openai.organization']
    openai.api_key = tokens['openai.api_key']

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

def message_autoflag(message):
    print(openai.Model.list())

class BadUserState(Enum):
    SUSPEND = auto()
    WARN = auto()
    NONE = auto()

def url_to_text(url):
    print(requests.get("http://stackoverflow.com").text)

if __name__ == '__main__':
    message_autoflag('aaaaaa')
