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
import ssl

from utils import *
from mod_report import *
from match import *
from appeal_report import *
import pickle as pkl
from datetime import date

# user database: {user_id: [username, num_warnings, num_suspends, num_reports]}



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

        ssl._create_default_https_context = ssl._create_unverified_context

        self.group_num = None
        self.mod_channels = {} # Map from guild to the mod channel id for that guild
        self.main_channels = {}
        self.reports = {} # Map from user IDs to the state of their report
        self.matches = Match()
        self.bad_users = {}
        self.appealed_tickets = set()
        self.log = {}
        self.read_user_information()
        self.mod_tickets = {}

        if os.path.exists('all_banned_word.pkl'):
            with open('all_banned_word.pkl', 'rb') as handle:
                self.banned_word = pkl.load(handle)
        else:
            self.banned_word = []
    
    def read_user_information(self):
        if os.path.exists('reported_user_info.pkl'):
            with open('reported_user_info.pkl', 'rb') as handle:
                self.reported_user_information = pkl.load(handle)
        else:
            self.reported_user_information = {}

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

        if is_debug():
            pass
            # for thread in self.mod_channel.threads:
            #     await thread.delete()
            # for thread in self.main_channel.threads:
            #     if thread.name.startswith('match-'): continue
            #     await thread.delete()

    async def handle_new_message(self, message):

        if message.author.id == self.user.id:
            return
        
        # check if message is in the main channel
        
        try:
            if not message.channel.name.startswith('match-'): return
        except:
            return

        content = message.content

        # replace unicode characters
        content = replace_unicode_from_text(content)
        
        # make content lowercase
        content = content.lower()

        print(f"Received message (fixed): {content}")
        # return

        # AI IMAGE STUFF
        images = await message_to_images(message)
        if len(images): 
            captions = images_to_captions(images)
            print(f"Received images (captioned): {captions}")
            for caption in captions:
                category = message_autoflag(caption)
                print(f"Autoflagged image `{caption}` as {category}")
                if category != 5:
                    print(f"Autoflagged image as {category}")
                    score = ai_score(caption, category)
                    print(f"AI score: {score}")

                    link = message.jump_url
                    m = re.search('/(\d+)/(\d+)/(\d+)', link)   
                    thread = self.main_channel.get_thread(int(m.group(2)))
                    self.log['reported_user'] = message.author
                    self.log['reported_message'] = caption
                    self.log['reported_thread'] = thread.name
                    self.log['reported_url'] = link
                    self.log['user'] = self.user
                    self.log['reason'] = reporting_categories[category - 1]
                    self.log['reported_category'] = reporting_categories[category - 1]
                    self.log['category_id'] = category
                    self.log['unmatch'] = False
                    self.log['reported_score'] = score
                    self.record_report()
                    if score is not None and score >= 50:
                        if score >= 90:
                            # TODO: Yilun HIGH priority, bot reports user
                            self.log['severity'] = 'High'
                        elif score >= 50:
                            # TODO: Yilun MEDIUM priority, bot reports user
                            self.log['severity'] = 'Medium'
                        await self.handle_report(self.log, self.reported_user_information, is_bot=True)

        # AI LINK STUFF
        if content:
            has_bad_link = has_bad_links(content)
            if has_bad_link:
                await message.delete()
                await message.author.send('Your message was deleted because it contained a link to a bad website. Please do not post links containing undesirable content.')
                # TODO: increment counter in database, if counter >= 5, suspend user (and user can appeal)

        # AI MESSAGE STUFF
        if content:
            category = message_autoflag(content)
            if category != 5:
                print(f"Autoflagged message as {category}")
                score = ai_score(content, category)
                print(f"AI score: {score}")
                
                link = message.jump_url
                m = re.search('/(\d+)/(\d+)/(\d+)', link)   
                thread = self.main_channel.get_thread(int(m.group(2)))
                self.log['reported_user'] = message.author
                self.log['reported_message'] = message.content
                self.log['reported_thread'] = thread.name
                self.log['reported_url'] = link
                self.log['user'] = self.user
                self.log['reason'] = reporting_categories[category - 1]
                self.log['reported_category'] = reporting_categories[category - 1]
                self.log['category_id'] = category
                self.log['unmatch'] = False
                self.log['reported_score'] = score
                self.record_report()
                if score is not None and score >= 50:
                    if score >= 90:
                        # TODO: Yilun HIGH priority, bot reports user
                        self.log['severity'] = 'High'
                    elif score >= 50:
                        # TODO: Yilun MEDIUM priority, bot reports user
                        self.log['severity'] = 'Medium'
                    await self.handle_report(self.log, self.reported_user_information, is_bot=True)

    def record_report(self):

        if self.log['reported_user'].id not in self.reported_user_information:
            self.reported_user_information[self.log['reported_user'].id] = {}
            self.reported_user_information[self.log['reported_user'].id]['num_report'] = 0
            self.reported_user_information[self.log['reported_user'].id]['warned'] = 0
        self.reported_user_information[self.log['reported_user'].id]['num_report'] +=1
        self.reported_user_information[self.log['reported_user'].id]['warned'] +=1
        self.reported_user_information[self.log['reported_user'].id]['last_report'] = date.today()

        suspect_id = self.log['reported_user'].id
        if suspect_id not in self.bad_users:
            self.bad_users[suspect_id] = {'state': BadUserState.NONE}

        print(self.reported_user_information)
        with open('reported_user_info.pkl', 'wb') as handle:
            pkl.dump(self.reported_user_information, handle)

    async def on_message_edit(self, before, after):
        if before.content != after.content:
            # print(f'User {before.author} edited a message from {before.content} to {after.content}.')
            await self.handle_new_message(after)         

    async def on_message(self, message):
        '''
        This function is called whenever a message is sent in a channel that the bot can see (including DMs). 
        Currently the bot is configured to only handle messages that are sent over DMs or in your group's "group-#" channel. 
        '''
        
        # Ignore messages from the bot 
        if message.author.id == self.user.id:
            return

        await self.handle_new_message(message)
        # fake_user = await self.username_to_user("ashto1")
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
        if message.channel.name == f'group-{self.group_num}-mod':
            # sending message to mod channel, patterns contains:
            # 1. ban xxx, remove ban xxx
            if message.content.startswith('regex add'):
                # banning a word
                print("banning")
                banned_word_index = message.content.index('add')+4
                banned_word = message.content[banned_word_index:]
                self.banned_word.append(banned_word)
                with open('all_banned_word.pkl', 'wb') as handle:
                    pkl.dump(self.banned_word, handle)
                await self.mod_channel.send(banned_word +' is banned')
            elif message.content.startswith('regex remove'):
                # removing ban of a word
                print("removing ban")
                banned_word_index = message.content.index('remove')+7
                banned_word = message.content[banned_word_index:]
                self.banned_word.remove(banned_word)
                with open('all_banned_word.pkl', 'wb') as handle:
                    pkl.dump(self.banned_word, handle)
                await self.mod_channel.send(banned_word+ ' ban is removed')
            elif message.content.startswith('regex list'):
                # listing all banned words
                print("listing ban")
                if len(self.banned_word) == 0:
                    await self.mod_channel.send("There are no banned words")
                else:
                    reply = 'The banned words are: '
                    for word in self.banned_word:
                        reply += (word+' ')
                    await self.mod_channel.send(reply)
            else:
                await self.mod_channel.send(f'You are sending message to mod channel, please send regex related command')
            return
        if not message.channel.name == f'group-{self.group_num}':
            for banned_word in self.banned_word:
                if banned_word in message.content:
                    await message.delete()

        # Forward the message to the mod channel
        # await self.mod_channel.send(f'Forwarded message:\n{message.author.name}: "{message.content}"')
        # scores = self.eval_text(message.content)
        # await self.mod_channel.send(self.code_format(scores))

    async def handle_report(self, report_information, reported_user_information, is_bot=False):
        
        if 'reported_score' not in report_information: 
            reported_message = report_information['reported_message']
            category_id = report_information['category_id']
            report_information['reported_score'] = ai_score(reported_message, category_id)
                           
        report_information['reported_user_state'] = BadUserState.NONE

        try:
            reported_user_id = report_information['reported_user'].id
            user_data = get_user_data_firebase(reported_user_id) # TODO: Matt firebase

            # TODO: replace with user_data information

            report_information['reported_user_state'] = self.bad_users[reported_user_id]['state']
        except:
            pass

        await handle_report_helper(report_information, reported_user_information, client, is_bot=is_bot)

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