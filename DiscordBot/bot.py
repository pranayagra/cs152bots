# bot.py
import discord
from discord.ext import commands
from discord.utils import get
import os
import json
import logging
import re
import requests
from report import Report
import pdb

from utils import *

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

class ModBot(discord.Client):
    def __init__(self): 
        intents = discord.Intents.default()
        intents.message_content = True
        intents.members = True
        super().__init__(command_prefix='.', intents=intents)
        self.group_num = None
        self.mod_channels = {} # Map from guild to the mod channel id for that guild
        self.reports = {} # Map from user IDs to the state of their report
        self.matches = Match()

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

        self.guild = self.get_guild(1103033282779676743)
        self.category = get_category_by_name(guild, 'Project Team Channels (1-24)')    
        

    async def on_message(self, message):
        '''
        This function is called whenever a message is sent in a channel that the bot can see (including DMs). 
        Currently the bot is configured to only handle messages that are sent over DMs or in your group's "group-#" channel. 
        '''
        # Ignore messages from the bot 
        if message.author.id == self.user.id:
            return

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
            reply += "Use the `match` command to match with a user.\n"
            reply += "Use the `unmatch` command to unmatch with a user.\n"
            await message.channel.send(reply)
            return

        author_id = message.author.id
        responses = []

        if message.content.startswith('match'):
            await self.handle_match_command(message)

        if message.content.startswith('unmatch'):
            await self.handle_unmatch_command(message)

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
            self.reports.pop(author_id)

    async def handle_channel_message(self, message):
        # Only handle messages sent in the "group-#" channel
        if not message.channel.name == f'group-{self.group_num}':
            return

        # Forward the message to the mod channel
        mod_channel = self.mod_channels[message.guild.id]
        await mod_channel.send(f'Forwarded message:\n{message.author.name}: "{message.content}"')
        scores = self.eval_text(message.content)
        await mod_channel.send(self.code_format(scores))

    async def handle_unmatch_command(self, message):
        user2_mention = message.content.split(' ')[1]

        guild = self.guild
        category = self.category

        user1 = message.author
        user2 = await self.username_to_user(user2_mention)

        if await check_issue(not user2, user1.send, f"Could not find {user2_mention}."): return
        if await check_issue(user1 == user2, user1.send, "You cannot unmatch with yourself."): return
        if await check_issue(not self.matches.is_match(user1, user2), f'No match with {user2}.'): return        

        channel_name = self.matches.get_match_channel_name(user1, user2)

        if await delete_channel(guild, channel_name):
            await user1.send(f"Unmatched with: {user2}")
            await user2.send(f"Unmatched with: {user1}")
        else:
            await user1.send(f'Failed to unmatch with {user2}.')          


    async def handle_match_command(self, message):
        # Extract the mentioned user from the message
        
        user2_mention = message.content.split(' ')[1]

        guild = self.guild
        category = self.category

        # await delete_channel(guild, 'match-198964576904019968-473356457929343007')

        user1 = message.author
        user2 = await self.username_to_user(user2_mention)

        if await check_issue(not user2, user1.send, f"Could not find {user2_mention}."): return
        if await check_issue(user1 == user2, user1.send, "You cannot match with yourself."): return

        # check if user1 is already matched with user2 or has already sent a match request to user2
        if await check_issue(self.matches.is_match(user1, user2), user1.send, f'You are already matched with {user2_mention}.'): return
        if await check_issue(self.matches.is_match_request(user1, user2), user1.send, f'You have already sent a match request to {user2_mention}.'): return

        if is_debug(): self.matches.add_match_request(user2, user1)

        self.matches.add_match_request(user1, user2)

        # if user2 has not already sent user1 a match request, send a match request to user2
        if not self.matches.is_match_request(user2, user1):
            try:
                match_dm = f"{user1} wants to match with you. Do you want to match back? (Y/N)"
                await user2.send(match_dm)
                await user1.send(f'Sent match request to {user2_mention}. A match will be created if {user2_mention} accepts.')
            except discord.Forbidden:
                if await check_issue(True, user1.send, f"Could not send a DM to {user2_mention}."): return

            try:
                response = await self.wait_for('message', check=check_DM, timeout=120.0)
                if response.content.lower() == 'y':
                    self.matches.add_match_request(user2, user1)
            except: 
                pass

        # both parties have matched, create a channel for them
        if self.matches.is_match(user1, user2):
            match_information = self.matches.get_match(user1, user2)
            try:
                channel = await match_information.create_text_channel(self.user, guild, category)
                await user1.send(f"A match channel has been created: {channel.mention}")
                await user2.send(f"A match channel has been created: {channel.mention}")
            except Exception as ee:
                print("Failed to create channel: ", ee)
                

        # if key_reverse_format not in self.user_sent_user_match:
        #     # Send the match DM to user2
        #     try:
        #         match_dm_channel = await user2.create_dm()
        #         await match_dm_channel.send(match_dm)
        #     except discord.Forbidden:
        #         await message.channel.send("I couldn't send a DM to the specified user.")
        #         return

        #     def check(m):
        #         return m.author == user2 and isinstance(m.channel, discord.DMChannel)

        #     try:
        #         # Wait for user2's response
        #         response = await self.wait_for('message', check=check, timeout=60.0)
        #         if response.content.lower() == 'y':
        #             self.user_sent_user_match.add(key_reverse_format)
        #         else:
        #             await user1.send(f"{user2.mention} declined the match.")                       
        #     except asyncio.TimeoutError:
        #         await user1.send("User did not respond in time.")

        # if key_reverse_format in self.user_sent_user_match:
        #     # Create a private channel between user1 and user2
        #     print(self.user_sent_user_match)
        #     print('make a groupchat between users')

        #     overwrites = {
        #         guild.default_role: discord.PermissionOverwrite(read_messages=False),
        #         user1: discord.PermissionOverwrite(read_messages=True),
        #         user2: discord.PermissionOverwrite(read_messages=True)
        #     }

        #     if name1 <= name2: channel_name = f'match-{name1}-{name2}'
        #     else: channel_name = f'match-{name2}-{name1}'  

        #     try:
        #         channel = await category.create_text_channel(channel_name, overwrites=overwrites)
        #         await user1.send(f"A match channel has been created: {channel.mention}")
        #         await user2.send(f"A match channel has been created: {channel.mention}")
        #     except:
        #         print('channel failed to create')

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