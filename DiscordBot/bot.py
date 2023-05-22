# bot.py
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

# from nextcord.ext import commands
# import nextcord

from utils import *
from mod_report import *
from match import *

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

class TicketOld:
    def __init__(self, message, report_information, reported_user_information):
        self.state = None
        self.claimed = False
        self.claimed_by = None
        self.owner_message = None
        self.communication_thread = None
        self.logs = []
        self.message = message
        self.report_information = report_information
        self.reported_user_information = reported_user_information

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
            report_information = self.reports[author_id].log
            reported_user_information = self.reports[author_id].reported_user_information
            pdb.set_trace()
            self.handle_report(report_information, reported_user_information)
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

    async def handle_report(self, report_information, reported_user_information, fake_user=None):
        '''
        This function is called when a report is complete. 
        It should do something with the report information, like send it to a channel or write it to a file.
        '''

        if is_debug(): report_information = {'severity': 'High', 'user': 'user', 'reported_user': 'reported_user', 'reported_category': 'reported_category', 'reason': 'reason', 'reported_message': 'reported_message', 'reported_channel': 'reported_channel', 'reported_url': 'https://discord.com/channels/1103033282779676743/1103033285786992690/1109612952211951647'}
        # report_information is a dictionary containing the following keys:
        # - "severity": the severity that the user gave for reporting the other user
        # - "user": the user who sent the report
        # - "reported_user": the user that was reported
        # - "reported_category": the category that the reported message was classified as
        # - "reason": the reason that the user gave for reporting the other user
        # - "reported_message": the message that the reported user sent
        # - "reported_channel": the channel that the reported user sent the message in
        # - "reported_url": a link to the reported message

        if is_debug(): report_information['user'] = fake_user
        if is_debug(): report_information['reported_user'] = fake_user
        
        report_information['reported_score'] = 'N/A' # reported_score: the score that the AI gave for the reported message

        # reported_user_information is a dictionary containing the following keys:
            # - "# of reports": the number of times the user has been reported
            # - "has been warned": whether or not the user has been warned before
            # - "last report": the last time the user was reported
            # ???

        ## BEGIN NEW WORKFLOW ##

        unclaimed_view = UnclaimedView()
        claimed_view = ClaimedView()
        
        ticket = Ticket(report_information, reported_user_information, self.mod_channel)
        ticket.mod_thread = await self.mod_channel.create_thread(
                name=f"mod-ticket-{ticket.reporter}-{ticket.suspect}", 
                type=discord.ChannelType.public_thread)

        ticket.main_message = await ticket.mod_thread.send(content=ticket.main_content(), view=unclaimed_view.view())

        async def claim_callback(interaction: discord.Interaction):
            if ticket.claimed: return

            ticket.set_claimed(interaction.user)
            await interaction.response.defer()
            unclaimed_view.disable_claim_button()

            if ticket.reporter_thread:
                await ticket.reporter_thread.add_user(ticket.claimed_by)

            await ticket.main_message.edit(content=ticket.main_content(), view=unclaimed_view.view())
            ticket.claimed_webhook_message = await interaction.followup.send(content=f"Ticket Claimed!", view=claimed_view.view(), ephemeral=True)
        
        async def unclaim_callback(interaction: discord.Interaction):
            if not ticket.claimed: return
            
            await interaction.response.defer()

            unclaimed_view.enable_claim_button()

            await ticket.set_unclaimed()
            await ticket.main_message.edit(content=ticket.main_content(), view=unclaimed_view.view())
            await interaction.followup.send(f'Ticket unclaimed by {interaction.user}.')       

        async def suspend_callback(interaction: discord.Interaction):
            if not ticket.claimed: return

            await interaction.response.defer()

            await ticket.set_unclaimed(state = TicketState.REPORT_COMPLETE)
            await interaction.followup.send(f'Reported user suspended by {interaction.user}.')
            await ticket.reporter.send(f'Your report against {ticket.suspect} has resulted in them being suspended.')
            await ticket.suspect.send(f'You have been suspended for {ticket.report_information["reason"]}.')

        async def false_report_callback(interaction: discord.Interaction):
            if not ticket.claimed: return

            await interaction.response.defer()
            
            await ticket.set_unclaimed(state = TicketState.REPORT_COMPLETE)
            await interaction.followup.send(f'Ticket marked as false report by {interaction.user}.')         

        async def create_thread_callback(interaction: discord.Interaction):
            if not ticket.claimed or ticket.reporter_thread: return

            await interaction.response.defer()

            ticket.reporter_thread = await self.mod_channel.create_thread(
                name=f"reporter-ticket-{ticket.reporter}-{ticket.suspect}", 
                type=discord.ChannelType.private_thread,
                invitable=True
            )
            await ticket.reporter_thread.add_user(ticket.reporter)
            await ticket.reporter_thread.add_user(ticket.claimed_by)

            claimed_view.disable_create_thread_button()
            ticket.claimed_webhook_message = await ticket.claimed_webhook_message.edit(view=claimed_view.view())
            await interaction.followup.send(f'Created private thread with reporter.')

        unclaimed_view.claim_button.callback = claim_callback
        claimed_view.set_callbacks(suspend_callback, false_report_callback, create_thread_callback, unclaim_callback)

        ## END NEW WORKFLOW ## 

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

        user1 = message.author
        user2 = await self.username_to_user(user2_mention)

        if await check_issue(not user2, user1.send, f"Could not find {user2_mention}."): return
        if await check_issue(user1 == user2, user1.send, "You cannot match with yourself."): return

        # check if user1 is already matched with user2 or has already sent a match request to user2
        if await check_issue(self.matches.is_match(user1, user2), user1.send, f'You are already matched with {user2_mention}.'): return
        if await check_issue(self.matches.is_match_request(user1, user2), user1.send, f'You have already sent a match request to {user2_mention}.'): return

        if is_debug() and False: self.matches.add_match_request(user2, user1)

        self.matches.add_match_request(user1, user2)

        # if user2 has not already sent user1 a match request, send a match request to user2
        if not self.matches.is_match_request(user2, user1):
            request_view = RequestView()
            match_dm = f"{user1} wants to match with you. Do you want to match back?"
            try:
                message = await user2.send(content=match_dm, view=request_view.view())
                await user1.send(f'Sent match request to {user2_mention}. A match will be created if {user2_mention} accepts.')
            except:
                if await check_issue(True, user1.send, f"Could not send a DM to {user2_mention}."): return

            async def accept_callback(interaction: discord.Interaction):
                accept_view = AcceptView()
                
                await interaction.response.defer()
                await message.edit(content=match_dm, view=accept_view.view())
                if not self.matches.is_match(user1, user2):
                    self.matches.add_match_request(user2, user1)
                    await self.handle_match(user1, user2)

            async def decline_callback(interaction: discord.Interaction):
                decline_view = DeclineView()
                await interaction.response.defer()
                await message.edit(content=match_dm, view=decline_view.view())

            request_view.accept_button.callback = accept_callback
            request_view.decline_button.callback = decline_callback

        if self.matches.is_match(user1, user2):
            await self.handle_match(user1, user2)

    async def handle_match(self, user1, user2):
        match_information = self.matches.get_match(user1, user2)
        try:

            match_thread = await self.main_channel.create_thread(
                name=f"match-{match_information.user1}-{match_information.user2}", 
                type=discord.ChannelType.private_thread,
                invitable=False
            )
            await match_thread.add_user(match_information.user1)
            await match_thread.add_user(match_information.user2)

            await match_information.user1.send(f"Matched with {match_information.user2}! Chat: {match_thread.mention}")
            await match_information.user2.send(f"Matched with {match_information.user1}! Chat: {match_thread.mention}")
        except Exception as e:
            print("Failed to create channel: ", e)

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