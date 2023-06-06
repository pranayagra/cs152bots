import discord
from discord import app_commands, utils
from discord.ext import commands
from discord.ui import Button, View
from discord.utils import get
from enum import Enum, auto
from utils import *

class AppealReportView:
    def __init__(self, client, mod_thread, appealer, ticket_id, ticket):
        self.unclaimed_view = UnclaimedAppealView()
        self.claimed_view = ClaimedAppealView()

        self.client = client
        self.mod_thread = mod_thread
        self.appealer = appealer
        self.ticket_id = ticket_id

        self.ticket = ticket

        self.category_id = ticket.category_id

        self.message = None
        self.claimed_webhook_message = None

        self.appeal_thread_name = f'appeal-{ticket_id}'
        self.appeal_thread = None

        self.claim_by = None

    def appeal_thread_message(self):
        interaction_message = ''
        if self.category_id == 1: # user is a bot
            interaction_message = 'Your account has been suspended for violating our community guidelines'
        elif self.category_id == 2: # user is pretending to be someone else
            interaction_message = 'You have 24 hours to submit a government ID with a photo. If your current pictures accurately represent who you are, no further action is needed. If your current pictures depict someone else, you must change all pictures to reflect genuine pictures of who you are. If you 1) do not submit an ID OR 2) your new pictures do not accurately represent who you are, your account will be suspended.'
        elif self.category_id == 3: # user is a minor
            interaction_message = 'minor'
        elif self.category_id == 4: # user is trying to ask for money 
            interaction_message = 'money'
        return interaction_message


    async def create_appeal_thread(self):
        self.appeal_thread = await self.client.main_channel.create_thread(
            name=self.appeal_thread_name, 
            type=discord.ChannelType.private_thread
            )        
        await self.appeal_thread.add_user(self.appealer)
        await self.appeal_thread.add_user(self.claim_by)  

        await self.appealer.send(f"Appeal Chat Created: {self.appeal_thread.mention}")
        await self.mod_thread.send(f"Appeal Chat Created: {self.appeal_thread.mention}")
        i_m = self.appeal_thread_message()
        if i_m: await self.appeal_thread.send(i_m)


    async def display_view(self):

        message_content = "An appeal has been submitted. Do you want to claim it?"
        try:
            self.message = await self.mod_thread.send(content=message_content, view=self.unclaimed_view.view())
            await self.appealer.send(f"Appealing ticket {self.ticket_id}... Please wait for a moderator to respond.")
        except Exception as e:
            print(e)
            if await check_issue(True, self.appealer.send, f"Could not send an appeal request."): return        

        async def claim_callback(interaction: discord.Interaction):
            await interaction.response.defer()

            self.unclaimed_view.disable_claim_button()
            self.claim_by = interaction.user
            await self.message.edit(content=message_content, view=self.unclaimed_view.view())
            await interaction.followup.send(f'Ticket claimed by {interaction.user}.') 
            await self.create_appeal_thread()
            self.claimed_webhook_message = await interaction.followup.send(content=f"Ticket Claimed!", view=self.claimed_view.view(), ephemeral=True)

        async def accept_appeal_callback(interaction: discord.Interaction):

            await interaction.response.defer()
            
            await interaction.followup.send(f'Appeal accepted by {interaction.user}.')
            await self.claimed_webhook_message.delete()
            await self.appeal_thread.send(f'User {self.appealer.mention} has been unsuspended.')
            await self.appeal_thread.edit(locked=True)

            try:
                bad_user = self.client.bad_users[self.appealer.id]
                bad_user.pop(self.ticket_id) # remove from bad users
                bad_user['state'] = BadUserState.NONE
            except:
                pass

            for thread in self.client.main_channel.threads:
                try:
                    await thread.fetch_member(self.appealer.id)
                    if thread.name.startswith('appeal-'): continue
                    await thread.edit(locked=False)
                    await thread.send(f'User {self.appealer.mention} has been unsuspended.')
                except:
                    pass

        async def decline_appeal_callback(interaction: discord.Interaction):
            await interaction.response.defer()

            await interaction.followup.send(f'Appeal rejected by {interaction.user}.')
            await self.claimed_webhook_message.delete()
            await self.appeal_thread.send(f'User {self.appealer.mention} appeal rejected.')
            await self.appeal_thread.edit(locked=True)

        self.unclaimed_view.claim_button.callback = claim_callback
        self.claimed_view.accept_button.callback = accept_appeal_callback
        self.claimed_view.reject_button.callback = decline_appeal_callback

class UnclaimedAppealView:
    def __init__(self):
        self.claim_button = Button(style=discord.ButtonStyle.green, label='Claim')
        self.unclaimed_view = View(timeout=None)
        self.unclaimed_view.add_item(self.claim_button)
    
    def view(self): return self.unclaimed_view

    def disable_claim_button(self):
        self.claim_button.disabled = True

class ClaimedAppealView:
    def __init__(self):
        self.accept_button = Button(style=discord.ButtonStyle.green, label='Accept Appeal')
        self.reject_button = Button(style=discord.ButtonStyle.red, label='Reject Appeal')
        self.claimed_view = View(timeout=None)
        self.claimed_view.add_item(self.accept_button)
        self.claimed_view.add_item(self.reject_button)

    def view(self): return self.claimed_view

    def disable_buttons(self):
        self.accept_button.disabled = True
        self.reject_button.disabled = True  
        

async def handle_appeal_command_helper(message, client):
    data = message.content.split()
    if await check_issue(len(data) < 2, message.author.send, "Please mention an id to appeal."): return
    ticket_id = data[1]
    if await check_issue(not ticket_id.isdigit(), message.author.send, "Please mention a valid id to appeal."): return
    ticket_id = int(ticket_id)

    suspect = message.author

    print(client.bad_users)
    print(ticket_id)

    try:
        ticket = client.bad_users[suspect.id][ticket_id]
    except:
        if await check_issue(True, suspect.send, "No appeal ticket found."): return

    if await check_issue(ticket_id in client.appealed_tickets, suspect.send, "This ticket has already been appealed."): return

    try:
        # for thread in client.mod_channel.threads: print(thread.name, thread.id)
        mod_thread = client.mod_channel.get_thread(ticket_id)
    except Exception as e:
        # print(e) 
        if await check_issue(True, suspect.send, f"No appeal thread found."): return
    
    client.appealed_tickets.add(ticket_id)

    appeal_report_view = AppealReportView(client, mod_thread, suspect, ticket_id, ticket)
    await appeal_report_view.display_view()
