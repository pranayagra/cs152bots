import discord
from discord import app_commands, utils
from discord.ext import commands
from discord.ui import Button, View
from discord.utils import get
from enum import Enum, auto
from utils import *


class RequestView:
    def __init__(self):
        self.accept_button = Button(style=discord.ButtonStyle.green, label='Yes')
        self.decline_button = Button(style=discord.ButtonStyle.red, label='No')
        self.request_view = View(timeout=None)
        self.request_view.add_item(self.accept_button)
        self.request_view.add_item(self.decline_button)
    
    def view(self): return self.request_view


class AcceptView:
    def __init__(self):
        self.accept_button = Button(style=discord.ButtonStyle.green, label='Yes')
        self.accept_button.disabled = True
        self.accept_view = View(timeout=None)
        self.accept_view.add_item(self.accept_button)
    
    def view(self): return self.accept_view

class DeclineView:
    def __init__(self):
        self.decline_button = Button(style=discord.ButtonStyle.red, label='No')
        self.decline_button.disabled = True
        self.decline_view = View(timeout=None)
        self.decline_view.add_item(self.decline_button)
    
    def view(self): return self.decline_view


class MatchInformation:
    def __init__(self, user1, user2):
        self.user1 = user1
        self.user2 = user2

        names = [user1.name, user2.name]
        names.sort()
        self.channel_name = f'match-{names[0]}-{names[1]}'

        self.channel = None

    async def create_text_channel(self, bot, guild, category):
        # print(bot, self.user1, self.user2, guild, category)
        overwrites = {
            guild.default_role: discord.PermissionOverwrite(read_messages=False),
            bot: discord.PermissionOverwrite(administrator=True),
            self.user1: discord.PermissionOverwrite(read_messages=True),
            self.user2: discord.PermissionOverwrite(read_messages=True)
        }

        self.channel = await category.create_text_channel(self.channel_name, overwrites=overwrites)
        return self.channel

    def __hash__(self):
        return hash((self.user1, self.user2))

    def __eq__(self, other):
        if not isinstance(other, type(self)): return NotImplemented
        return self.channel_name == other.channel_name

    def __repr__(self):
        return f'MatchInformation({self.user1}, {self.user2})'
        

# make a match python class that has a set()
class Match:
    def __init__(self):
        self.match_requests = set()
        self.all_matches = {}

    def add_match_request(self, user1, user2):
        self.match_requests.add((user1, user2))
        if self.is_match_request(user2, user1):
            self.add_match(user1, user2)

    def remove_match_request(self, user1, user2):
        self.match_requests.remove((user1, user2))

    def is_match_request(self, user1, user2):
        return (user1, user2) in self.match_requests

    def add_match(self, user1, user2):
        names = [user1.name, user2.name]
        names.sort()
        self.all_matches[(names[0], names[1])] = MatchInformation(user1, user2)

    def remove_match(self, user1, user2):
        names = [user1.name, user2.name]
        names.sort()
        del self.all_matches[(names[0], names[1])]

    def is_match(self, user1, user2):
        names = [user1.name, user2.name]
        names.sort()
        return (names[0], names[1]) in self.all_matches

    def get_match(self, user1, user2):
        names = [user1.name, user2.name]
        names.sort()
        return self.all_matches[(names[0], names[1])]

    def get_match_channel_name(self, user1, user2):
        if self.is_match(user1, user2):
            return self.get_match(user1, user2).channel_name
