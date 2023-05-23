import discord
from discord import app_commands, utils
from discord.ext import commands
from discord.ui import Button, View
from discord.utils import get
import os
import json
import logging
import re
import requests
from report import Report
import pdb
from enum import Enum, auto


from utils import *
from mod_report import *
from match import *
from appeal_report import *

# Set up logging to the console
logger = logging.getLogger('discord')
logger.setLevel(logging.DEBUG)
handler = logging.FileHandler(filename='discord.log', encoding='utf-8', mode='w')
handler.setFormatter(logging.Formatter('%(asctime)s:%(levelname)s:%(name)s: %(message)s'))
logger.addHandler(handler)

# There should be a file called 'tokens.json' inside the same folder as this file
token_path = 'tokens.json'
if not os.path.isfile(token_path):
    raise Exception(f"{token_path} not found!")
with open(token_path) as f:
    # If you get an error here, it means your token is formatted incorrectly. Did you put it in quotes?
    tokens = json.load(f)
    discord_token = tokens['discord']

# class BadUser:
#     def __init__(self, state):
#         self.reports = {}
#         self.state = state

#     def add_ticket(self, ticket_id, ticket):
#         self.reports[ticket_id] = ticket

#     def warn(self):
#         self.state = BadUserState.WARN

#     def suspend(self):
#         self.state = BadUserState.SUSPENDED
    
#     def can_appeal(self):
        


class ModBot(discord.Client):
    def __init__(self): 
        intents = discord.Intents.default()
        intents.message_content = True
        intents.members = True
        super().__init__(command_prefix='.', intents=intents)
        self.group_num = None
        self.mod_channels = {} # Map from guild to the mod channel id for that guild
        self.main_channels = {}
        self.reports = {} # Map from user IDs to the state of their report
        self.matches = Match()
        self.bad_users = {}
        self.appealed_tickets = set()

    async def username_to_user(self, username):
        name = self.guild.get_member_named(username)
        if name is None: return False
        return await self.fetch_user(name.id)       

    async def on_ready(self):
        print(f'{self.user.name} has connected to Discord! It is these guilds:')
        for guild in self.guilds:
            print(f' - {guild.name}')
        print('Press Ctrl-C to quit.')

        # Parse the group number out of the bot's name
        match = re.search('[gG]roup (\d+) [bB]ot', self.user.name)
        if match:
            self.group_num = match.group(1)
        else:
            raise Exception("Group number not found in bot's name. Name format should be \"Group # Bot\".")

        # Find the mod channel in each guild that this bot should report to
        for guild in self.guilds:
            for channel in guild.text_channels:
                if channel.name == f'group-{self.group_num}-mod':
                    self.mod_channels[guild.id] = channel
                elif channel.name == f'group-{self.group_num}':
                    self.main_channels[guild.id] = channel

        self.guild = self.get_guild(1103033282779676743)
        self.category = get_category_by_name(guild, 'Project Team Channels (1-24)')   
        self.mod_channel = self.mod_channels[self.guild.id] 
        self.main_channel = self.main_channels[self.guild.id]

        if is_debug(): pass
            # for thread in self.mod_channel.threads:
            #     await thread.delete()
            # for thread in self.main_channel.threads:
            #     if thread.name.startswith('match-'): continue
            #     await thread.delete()

    async def on_message(self, message):
        '''
        This function is called whenever a message is sent in a channel that the bot can see (including DMs). 
        Currently the bot is configured to only handle messages that are sent over DMs or in your group's "group-#" channel. 
        '''
        # Ignore messages from the bot 
        if message.author.id == self.user.id:
            return

        fake_user = await self.username_to_user("ashto1")
        # await self.handle_report(None, None, fake_user)

        # Check if this message was sent in a server ("guild") or if it's a DM
        if message.guild:
            await self.handle_channel_message(message)
        else:
            await self.handle_dm(message)

    async def handle_dm(self, message):
        # Handle a help message
        if message.content == Report.HELP_KEYWORD:
            reply =  "Use the `report` command to begin the reporting process.\n"
            reply += "Use the `cancel` command to cancel the report process.\n"
            reply += "Use the `match <user>` command to match with a user.\n"
            reply += "Use the `unmatch <user>` command to unmatch with a user.\n"
            reply += "Use the `appeal <id>` command to appeal a ticket report.\n"
            await message.channel.send(reply)
            return

        author_id = message.author.id
        responses = []

        if message.content.startswith('match'):
            await self.handle_match_command(message)

        if message.content.startswith('unmatch'):
            await self.handle_unmatch_command(message)

        if message.content.startswith('appeal'):
            await self.handle_appeal_command(message)

        if is_debug() and message.content.startswith('dreport'):
            await self.handle_report(None, None, message.author)

        # Only respond to messages if they're part of a reporting flow
        if author_id not in self.reports and not message.content.startswith(Report.START_KEYWORD):
            return

        # If we don't currently have an active report for this user, add one
        if author_id not in self.reports:
            self.reports[author_id] = Report(self)

        # Let the report class handle this message; forward all the messages it returns to uss
        responses = await self.reports[author_id].handle_message(message)
        for r in responses:
            await message.channel.send(r)

        # If the report is complete or cancelled, remove it from our map
        if self.reports[author_id].report_complete():
            if not self.reports[author_id].cancel:
                report_information = self.reports[author_id].log
                reported_user_information = self.reports[author_id].reported_user_information
                # pdb.set_trace()
                await self.handle_report(report_information, reported_user_information)
            self.reports.pop(author_id)

    async def handle_channel_message(self, message):
        # Only handle messages sent in the "group-#" channel
        if not message.channel.name == f'group-{self.group_num}':
            return

        # Forward the message to the mod channel
        await self.mod_channel.send(f'Forwarded message:\n{message.author.name}: "{message.content}"')
        scores = self.eval_text(message.content)
        await self.mod_channel.send(self.code_format(scores))

    async def handle_report(self, report_information, reported_user_information, fake_user=None):
        
        if is_debug(): report_information, reported_user_information = encode_fake_information(report_information, reported_user_information, fake_user)
        
        report_information['reported_score'] = 'N/A'
        report_information['reported_user_state'] = BadUserState.NONE

        try:
            reported_user_id = report_information['reported_user'].id
            report_information['reported_user_state'] = self.bad_users[reported_user_id]['state']
        except:
            pass

        await handle_report_helper(report_information, reported_user_information, client)

    async def handle_unmatch_command(self, message):
        await handle_unmatch_command_helper(message, self)      

    async def handle_match_command(self, message):
        await handle_match_command_helper(message, self)

    async def handle_appeal_command(self, message):
        await handle_appeal_command_helper(message, self)

    def eval_text(self, message):
        ''''
        TODO: Once you know how you want to evaluate messages in your channel, 
        insert your code here! This will primarily be used in Milestone 3. 
        '''
        return message

    
    def code_format(self, text):
        ''''
        TODO: Once you know how you want to show that a message has been 
        evaluated, insert your code here for formatting the string to be 
        shown in the mod channel. 
        '''
        return "Evaluated: '" + text+ "'"


client = ModBot()

client.run(discord_token)