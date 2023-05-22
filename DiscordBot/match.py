import discord
from discord import app_commands, utils
from discord.ext import commands
from discord.ui import Button, View
from discord.utils import get
from enum import Enum, auto
from utils import *

class MatchRequestView:
    def __init__(self, user1, user2, client):
        self.user1 = user1
        self.user2 = user2
        self.message = None
        self.client = client

        self.request_view = RequestView()
        self.accept_view = AcceptView()
        self.decline_view = DeclineView()

        self.current_view = self.request_view

        self.match_dm = f"{self.user1.mention} wants to match with you. Do you want to match back?"

    async def display_view(self):
        try:
            self.message = await self.user2.send(content=self.match_dm, view=self.current_view.view())
            await self.user1.send(f'Sent match request to {self.user2.mention}! A match will be created if the request is accepted.')
        except:
            if await check_issue(True, self.user1.send, f"Could not send a DM to {self.user2.mention}."): return        

        async def accept_callback(interaction: discord.Interaction):
            self.current_view = self.accept_view
            await interaction.response.defer()
            await self.message.edit(content=self.match_dm, view=self.current_view.view())

            if not self.client.matches.is_match(self.user1, self.user2):
                self.client.matches.add_match_request(self.user2, self.user1)
                match_information = self.client.matches.get_match(self.user1, self.user2)
                await match_information.create_thread(self.client)

        async def decline_callback(interaction: discord.Interaction):
            self.current_view = self.decline_view
            await interaction.response.defer()
            await self.message.edit(content=self.match_dm, view=self.current_view.view())

        self.request_view.accept_button.callback = accept_callback
        self.request_view.decline_button.callback = decline_callback


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
        self.thread_name = f'match-{names[0]}-{names[1]}'

        self.thread = None

    async def create_thread(self, client):
        self.thread = await client.main_channel.create_thread(
                name=self.thread_name, 
                type=discord.ChannelType.private_thread,
                invitable=False
        )
        await self.thread.add_user(self.user1)
        await self.thread.add_user(self.user2)  

        await self.user1.send(f"Matched with {self.user2.mention}! Chat: {self.thread.mention}")
        await self.user2.send(f"Matched with {self.user1.mention}! Chat: {self.thread.mention}") 

    async def delete_thread(self):
        await self.thread.delete()
        self.thread = None

    def __hash__(self):
        return hash((self.user1, self.user2))

    def __eq__(self, other):
        if not isinstance(other, type(self)): return NotImplemented
        return self.thread_name == other.thread_name

    def __repr__(self):
        return f'MatchInformation({self.user1}, {self.user2})'
        
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


async def handle_match_command_helper(message, client):
    # Extract the mentioned user from the message
    data = message.content.split()
    if await check_issue(len(data) < 2, message.author.send, "Please mention a user to match with."): return
    user2_mention = data[1]

    user1 = message.author
    user2 = await client.username_to_user(user2_mention)
    
    try:
        state = client.bad_users[user1.id]['state']
        if await check_issue(state.startswith('suspended'), user1.send, f"You are suspended"): return
    except:
        pass

    if await check_issue(not user2, user1.send, f"Could not find {user2_mention}."): return
    if await check_issue(user1 == user2, user1.send, "You cannot match with yourself."): return

    # check if user1 is already matched with user2 or has already sent a match request to user2
    if await check_issue(client.matches.is_match(user1, user2), user1.send, f'You are already matched with {user2.mention}.'): return
    if await check_issue(client.matches.is_match_request(user1, user2), user1.send, f'You have already sent a match request to {user2.mention}.'): return

    client.matches.add_match_request(user1, user2)

    # if user2 has not already sent user1 a match request, send a match request to user2
    if not client.matches.is_match_request(user2, user1):
        match_request_view = MatchRequestView(user1, user2, client)
        await match_request_view.display_view()

    if client.matches.is_match(user1, user2):
        match_information = client.matches.get_match(user1, user2)
        await match_information.create_thread(client)    

async def handle_unmatch_command_helper(message, client):
        data = message.content.split()
        if await check_issue(len(data) < 2, message.author.send, "Please mention a user to unmatch with."): return
        user2_mention = data[1]      

        user1 = message.author
        user2 = await client.username_to_user(user2_mention)

        if await check_issue(not user2, user1.send, f"Could not find {user2_mention}."): return
        if await check_issue(user1 == user2, user1.send, "You cannot unmatch with yourself."): return
        if await check_issue(not client.matches.is_match(user1, user2), user1.send, f'No match with {user2.mention}.'): return        

        match_information = client.matches.get_match(user1, user2)
        await match_information.delete_thread()
        client.matches.remove_match(user1, user2)

        if match_information.thread is None:
            await user1.send(f"Unmatched with {user2}")
            await user2.send(f"Unmatched with {user1}")
        else:
            await user1.send(f'Failed to unmatch with {user2.mention}.')       