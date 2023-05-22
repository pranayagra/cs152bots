import discord
from discord import app_commands, utils
from discord.ext import commands
from discord.ui import Button, View
from discord.utils import get
from enum import Enum, auto
from utils import *

class UnclaimedView:
    def __init__(self):
        self.claim_button = Button(style=discord.ButtonStyle.green, label='Claim')
        self.unclaimed_view = View(timeout=None)
        self.unclaimed_view.add_item(self.claim_button)
    
    def view(self): return self.unclaimed_view

    def disable_claim_button(self):
        self.claim_button.disabled = True
    
    def enable_claim_button(self):
        self.claim_button.disabled = False


class ClaimedView:
    def __init__(self):
        suspend_button = Button(style=discord.ButtonStyle.red, label='Suspend Reported User')
        # warn_button = Button(style=discord.ButtonStyle.red, label='Warn Reported User')
        false_report_button = Button(style=discord.ButtonStyle.red, label='False Report')
        create_thread_button = Button(style=discord.ButtonStyle.blurple, label='Create Reporter Thread')
        unclaim_button = Button(style=discord.ButtonStyle.gray, label='Unclaim Ticket')
        self.owner_buttons = [suspend_button, false_report_button, create_thread_button, unclaim_button]   

        self.claimed_view = View(timeout=None)
        for button in self.owner_buttons:
            self.claimed_view.add_item(button)

    def view(self): return self.claimed_view

    def disable_create_thread_button(self):
        self.owner_buttons[2].disabled = True
    
    def enable_create_thread_button(self):
        self.owner_buttons[2].disabled = False
    
    def set_callbacks(self, suspend_callback, false_report_callback, create_thread_callback, unclaim_callback):
        self.owner_buttons[0].callback = suspend_callback
        self.owner_buttons[1].callback = false_report_callback
        self.owner_buttons[2].callback = create_thread_callback
        self.owner_buttons[3].callback = unclaim_callback


class TicketAction(Enum):
    FALSE_REPORT = auto()
    WARN_USER = auto()
    BAN_USER = auto()
    TBD = auto()


class TicketState(Enum):
    REPORT_UNCLAIMED = auto()
    REPORT_CLAIMED = auto()
    REPORT_COMPLETE = auto()
    REPORT_APPEAL = auto()

class Ticket:
    def __init__(self, report_information, reported_user_information):
        self.report_information = report_information
        self.reported_user_information = reported_user_information

        self.main_message = None
        self.main_message_text = format_ticket_message(report_information)

        self.reporter = report_information['user']
        self.suspect = report_information['reported_user']

        self.state = TicketState.REPORT_UNCLAIMED

        self.claimed = False
        self.claimed_by = None
        self.claimed_webhook_message = None
        
        self.mod_thread_name = f"mod-ticket-{self.reporter}-{self.suspect}"
        self.mod_thread = None
        self.mod_thread_id = None

        self.reporter_thread_name = f"reporter-ticket-{self.reporter}-{self.suspect}"
        self.reporter_thread = None

        self.mod_action = TicketAction.TBD
        self.appeal_status = None # not used currently

    def set_claimed(self, claimed_by, state = TicketState.REPORT_CLAIMED):
        self.claimed = True
        self.claimed_by = claimed_by
        self.state = state

    async def set_unclaimed(self, state = TicketState.REPORT_UNCLAIMED):
        self.claimed = False
        self.claimed_by = None
        self.state = state
        if self.claimed_webhook_message: 
            await self.claimed_webhook_message.delete()
        self.claimed_webhook_message = None

    def set_state(self, state):
        self.state = state

    def main_content(self):
        prepend_text = ''
        if self.state == TicketState.REPORT_UNCLAIMED:
            prepend_text = new_report_prepend()
        elif self.state == TicketState.REPORT_CLAIMED:
            prepend_text = claimed_report_prepend(self.claimed_by)
        elif self.state == TicketState.REPORT_COMPLETE:
            prepend_text = claimed_report_prepend(self.claimed_by)
        elif self.state == TicketState.REPORT_APPEAL:
            prepend_text = claimed_report_prepend(self.claimed_by)

        return f'{prepend_text}{self.main_message_text}'

    async def create_mod_thread(self, client):
        self.mod_thread = await client.mod_channel.create_thread(
            name=self.mod_thread_name, 
            type=discord.ChannelType.public_thread
            )
        self.mod_thread_id = self.mod_thread.id

    async def create_reporter_thread(self, client):
        self.reporter_thread = await client.main_channel.create_thread(
            name=self.reporter_thread_name, 
            type=discord.ChannelType.private_thread
            )        
        await self.reporter_thread.add_user(self.reporter)   
        await self.reporter_thread.add_user(self.claimed_by) 

    def save_ticket_to_file(self):
        suspect = self.suspect 
        ticket_id = self.ticket_id
        filename = None
        

def new_report_prepend():
    return f'New report ticket! Click the Claim button to claim the ticket.\n'

def claimed_report_prepend(claimer):
    return f'This ticket has been claimed by {claimer.mention}.\n'

def format_ticket_message(report_information):
    return f"""
    **Severity**: {report_information['severity']}
    **Reporter**: {report_information['user']}
    **Suspect**: {report_information['reported_user']}

    **Category**: {report_information['reported_category']}
    **Reason**: {report_information['reason']}
    **Message**: ```{report_information['reported_message']}```
    **Thread**: {report_information['reported_thread']}
    **Link**: {report_information['reported_url']}

    **AI Score**: {report_information['reported_score']}
    """

def format_reported_user_information(suspect, reported_user_information):
    prepend = f'**REPORT HISTORY {suspect.mention}**\n'
    body = f"""
    **Suspect**: {suspect}
    **Number of Reports**: {reported_user_information['num_report']}
    **Has Been Warned**: {reported_user_information['warned'] > 0}
    **Last Report**: {reported_user_information['last_report']}
    """
    return f'{prepend}{body}'

async def handle_report_helper(report_information, reported_user_information, client):
    unclaimed_view = UnclaimedView()
    claimed_view = ClaimedView()

    ticket = Ticket(report_information, reported_user_information)
    await ticket.create_mod_thread(client)

    ticket.main_message = await ticket.mod_thread.send(content=ticket.main_content(), view=unclaimed_view.view())

    await ticket.mod_thread.send(content=format_reported_user_information(ticket.suspect, reported_user_information))

    async def claim_callback(interaction: discord.Interaction):
        if ticket.claimed: return

        ticket.set_claimed(interaction.user)
        await interaction.response.defer()
        unclaimed_view.disable_claim_button()

        if ticket.reporter_thread:
            await ticket.reporter_thread.add_user(ticket.claimed_by)

        await ticket.main_message.edit(content=ticket.main_content(), view=unclaimed_view.view())
        await interaction.followup.send(f'Ticket claimed by {interaction.user}.')  
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
        ticket.set_action = TicketAction.BAN_USER
        await ticket.set_unclaimed(state = TicketState.REPORT_COMPLETE)
        await interaction.followup.send(f'Reported user suspended by {interaction.user}.')
        await ticket.reporter.send(f'Your report against {ticket.suspect} has resulted in them being suspended.')
        await ticket.suspect.send(f'You have been suspended for {ticket.report_information["reason"]}. If this is a mistake, please type `appeal {ticket.mod_thread_id}`.')

        # delete user from all their threads
        if ticket.suspect.id not in client.bad_users:
            client.bad_users[ticket.suspect.id] = {}
        bad_user = client.bad_users[ticket.suspect.id]
        bad_user[ticket.mod_thread_id] = ticket
        bad_user['state'] = 'suspended'

        for thread in client.main_channel.threads:
            try:
                await thread.fetch_member(ticket.suspect.id)
                if thread.name.startswith('appeal-'): continue
                await thread.edit(locked=True)
                await thread.send(f'User {ticket.suspect.mention} has been suspended.')
            except:
                pass


    async def false_report_callback(interaction: discord.Interaction):
        if not ticket.claimed: return

        await interaction.response.defer()
        ticket.set_action = TicketAction.FALSE_REPORT
        await ticket.set_unclaimed(state = TicketState.REPORT_COMPLETE)
        await interaction.followup.send(f'Ticket marked as false report by {interaction.user}.')             

    async def create_thread_callback(interaction: discord.Interaction):
        if not ticket.claimed or ticket.reporter_thread: return

        await interaction.response.defer()

        await ticket.create_reporter_thread(client)
        claimed_view.disable_create_thread_button()
        ticket.claimed_webhook_message = await ticket.claimed_webhook_message.edit(view=claimed_view.view())
        await interaction.followup.send(f'Created private thread with reporter:s {ticket.reporter_thread.mention}')

    unclaimed_view.claim_button.callback = claim_callback
    claimed_view.set_callbacks(suspend_callback, false_report_callback, create_thread_callback, unclaim_callback)        

def encode_fake_information(report_information, reported_user_information, fake_user):
    if not report_information and is_debug():
        report_information = {
                'severity': 'Medium',
                'user': fake_user,
                'reported_user': fake_user,
                'reported_category': 'hate_speech',
                'reason': 'hate_speech',
                'reported_message': 'I hate you',
                'reported_thread': None,
                'reported_url': 'https://discord.com/channels/1103033282779676743/1110074710999445534/1110074729659904050',
        }

    if True or not reported_user_information and is_debug():
        reported_user_information = {
            'num_report': 1,
            'warned': 2,
            'last_report': None,
        }
    return report_information, reported_user_information