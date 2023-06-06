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
        self.create_thread_button = Button(style=discord.ButtonStyle.blurple, label='Create Reporter Thread')
        self.accept_button = Button(style=discord.ButtonStyle.red, label='Accept Report')
        self.reject_button = Button(style=discord.ButtonStyle.red, label='Reject Report')
        self.unclaim_button = Button(style=discord.ButtonStyle.gray, label='Unclaim Ticket')

        self.claimed_view = View(timeout=None)
        self.claimed_view.add_item(self.create_thread_button)
        self.claimed_view.add_item(self.accept_button)
        self.claimed_view.add_item(self.reject_button)
        self.claimed_view.add_item(self.unclaim_button)

    def view(self): return self.claimed_view

    def disable_create_thread_button(self):
        self.create_thread_button.disabled = True
    
    def enable_create_thread_button(self):
        self.create_thread_button.disabled = False
    
    def set_callbacks(self, create_thread_callback, accept_callback, reject_callback, unclaim_callback):
        self.create_thread_button.callback = create_thread_callback
        self.accept_button.callback = accept_callback
        self.reject_button.callback = reject_callback
        self.unclaim_button.callback = unclaim_callback

class TicketActionState(Enum):
    ACTION_NONE = auto()
    ACTION_ACCEPTED = auto()
    ACTION_REJECTED = auto()

class TicketReportState(Enum):
    REPORT_UNCLAIMED = auto()
    REPORT_CLAIMED = auto()
    REPORT_COMPLETE = auto()

class TicketAppealState(Enum):
    APPEAL_NONE = auto()
    APPEAL_PENDING = auto()
    APPEAL_ACCEPTED = auto()
    APPEAL_REJECTED = auto()


'''
report_information = {
    'user': user,
    'reported_user': reported_user,
    'reported_user_state': reported_user_state,
    'category_id': category_id

}
'''

# Should accepted, rejected, appealed, successful appeal be added?
class Ticket:
    def __init__(self, report_information, reported_user_information, is_bot = False):
        self.report_information = report_information
        self.reported_user_information = reported_user_information
        self.is_bot = is_bot
        self.has_been_warned = report_information['reported_user_state'] == BadUserState.WARN # TODO: Matt replace with user-data database

        self.ai_score = report_information['reported_score']

        self.main_message = None # created soon after ticket is created
        self.main_message_text = format_ticket_message(report_information)

        self.reporter = report_information['user']
        self.suspect = report_information['reported_user']
        self.category_id = report_information['category_id']

        # set if ticket is claimed
        self.claimed = False 
        self.claimed_by = None
        self.claimed_webhook_message = None
        
        self.mod_thread_name = f"mod-ticket-{self.reporter}-{self.suspect}"
        self.mod_thread = None # created soon after ticket is created
        self.mod_thread_id = None # created soon after ticket is created (ID)

        self.reporter_thread_name = f"reporter-ticket-{self.reporter}-{self.suspect}"
        self.reporter_thread = None # created upon button press

        # updated throughout ticket lifecycle
        self.report_state = TicketReportState.REPORT_UNCLAIMED
        self.action_state = TicketActionState.ACTION_NONE
        self.appeal_state = TicketAppealState.APPEAL_NONE

    # TODO(Pranay): verify correct stuff is logged
    def to_dict(self):
        # Convert the class to a dictionary. 
        # Note: We convert the enums to strings here for serialization
        return {
            # 'report_information': self.report_information,
            # 'reported_user_information': self.reported_user_information,
            'is_bot': self.is_bot,
            'has_been_warned': self.has_been_warned,
            'ai_score': self.ai_score,
            # 'main_message': self.main_message, #####
            'main_message_text': self.main_message_text,
            'reporter_id': self.reporter.id,
            'suspect_id': self.suspect.id,
            'category_id': self.category_id,
            'claimed': self.claimed,
            'claimed_by': str(self.claimed_by), ####
            # 'claimed_webhook_message': self.claimed_webhook_message, ####
            'mod_thread_name': self.mod_thread_name,
            # 'mod_thread': self.mod_thread,
            'mod_thread_id': self.mod_thread_id,
            'reporter_thread_name': self.reporter_thread_name,
            # 'reporter_thread': self.reporter_thread,
            'report_state': self.report_state.name,
            'action_state': self.action_state.name,
            'appeal_state': self.appeal_state.name
        }

    def set_claimed(self, claimed_by):
        self.claimed = True
        self.claimed_by = claimed_by
        self.report_state = TicketReportState.REPORT_CLAIMED

    async def set_unclaimed(self):
        self.claimed = False
        self.claimed_by = None
        self.report_state = TicketReportState.REPORT_UNCLAIMED
        if self.claimed_webhook_message: 
            await self.claimed_webhook_message.delete()
        self.claimed_webhook_message = None

    async def complete_report(self):
        self.report_state = TicketReportState.REPORT_COMPLETE
        if self.claimed_webhook_message: 
            await self.claimed_webhook_message.delete()
        self.claimed_webhook_message = None

    def main_content(self):
        prepend_text = ''
        if self.report_state == TicketReportState.REPORT_UNCLAIMED:
            prepend_text = unclaimed_report_prepend()
        else:
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


def unclaimed_report_prepend():
    return f'New report ticket! Click the Claim button to claim the ticket.\n'

def claimed_report_prepend(claimer):
    return f'This ticket has been claimed by {claimer.mention}.\n'

def format_ticket_message(report_information):
    return f"""
    **Severity**: {report_information['severity']}
    **Reporter**: {report_information['user']}
    **Suspect**: {report_information['reported_user']}
    **Suspect State**: {report_information['reported_user_state'].name}

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
    """
    # **Number of Reports**: {reported_user_information['num_report']}
    # **Has Been Warned**: {reported_user_information['warned'] > 0}
    # **Last Report**: {reported_user_information['last_report']}
    return f'{prepend}{body}'



def accept_report_workflow(ticket):
    interaction_message = ''
    reporter_message = ''
    suspect_message = ''
    action = ''

    category_id = ticket.category_id
    mod_user = ticket.claimed_by
    reported_user = ticket.reporter
    suspect_user = ticket.suspect
    has_been_warned = ticket.has_been_warned
    is_bot = ticket.is_bot

    if category_id == 1: # user is a bot
        interaction_message = f'Reported user banned by {mod_user}.'
        reporter_message = f'Your report against {suspect_user} has resulted in them being banned.'
        suspect_message = f'Your account has been suspended for violating our community guidelines as bots are not allowed.'
        action = 'ban'
    elif category_id == 2: # pretending to be someone else
        interaction_message = f'Reported user banned by {mod_user}.'
        reporter_message = f'Your report against {suspect_user} has resulted in them being banned.'
        suspect_message = f'Your account has been suspended for violating our community guidelines as impersonation is not allowed.'
        action = 'ban'
    elif category_id == 3: # user is a minor
        interaction_message = f'Reported user banned by {mod_user}.'
        reporter_message = f'Your report against {suspect_user} has resulted in them being banned.'
        suspect_message = f'Your account has been suspended for violating our community guidelines as minors are not allowed.'
        action = 'ban'
    elif category_id == 4: # user is trying to ask for money
        if has_been_warned:
            interaction_message = f'Reported user banned by {mod_user}.'
            reporter_message = f'Your report against {suspect_user} has resulted in them being banned.'
            suspect_message = f'Your account has been suspended for violating our community guidelines as you are not allowed to ask for money.'
            action = 'ban'
        else:
            interaction_message = f'Reported user warned by {mod_user}.'
            reporter_message = f'Your report against {suspect_user} has resulted in them being warned.'
            suspect_message = f'Your account has been warned for violating our community guidelines as you are not allowed to ask for money. If you do this again, you will be banned.'
            action = 'warn'

    if is_bot:
        reporter_message = ''

    return interaction_message, reporter_message, suspect_message, action


async def handle_report_helper(report_information, reported_user_information, client, is_bot=False):
    unclaimed_view = UnclaimedView()
    claimed_view = ClaimedView()

    ticket = Ticket(report_information, reported_user_information, is_bot)
    await ticket.create_mod_thread(client)

    client.mod_tickets[ticket.mod_thread_id] = ticket

    update_ticket_firebase(ticket.mod_thread_id, ticket)

    ticket.main_message = await ticket.mod_thread.send(content=ticket.main_content(), view=unclaimed_view.view())

    await ticket.mod_thread.send(content=format_reported_user_information(ticket.suspect, reported_user_information)) 
    
    update_ticket_firebase(ticket.mod_thread_id, ticket)


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
        update_ticket_firebase(ticket.mod_thread_id, ticket)

    async def unclaim_callback(interaction: discord.Interaction):
        if not ticket.claimed: return
        
        await interaction.response.defer()

        unclaimed_view.enable_claim_button()

        await ticket.set_unclaimed()
        await ticket.main_message.edit(content=ticket.main_content(), view=unclaimed_view.view())
        await interaction.followup.send(f'Ticket unclaimed by {interaction.user}.')
        update_ticket_firebase(ticket.mod_thread_id, ticket)

    async def accept_callback(interaction: discord.Interaction):
        if not ticket.claimed: return

        await interaction.response.defer()

        ticket.action_state = TicketActionState.ACTION_ACCEPTED
        await ticket.complete_report()

        category_id = ticket.category_id
        interaction_message, reporter_message, suspect_message, action = accept_report_workflow(ticket)

        await interaction.followup.send(interaction_message)
        await ticket.suspect.send(suspect_message)
        await ticket.suspect.send(f'If this is a mistake, please type `appeal {ticket.mod_thread_id}`.')
        if reporter_message: await ticket.reporter.send(reporter_message)

        bad_user = client.bad_users[ticket.suspect.id]
        bad_user[ticket.mod_thread_id] = ticket
        if action == 'warn':
            bad_user['state'] = BadUserState.WARN
        else:
            bad_user['state'] = BadUserState.SUSPEND
            for thread in client.main_channel.threads:
                try:
                    await thread.fetch_member(ticket.suspect.id)
                    if thread.name.startswith('appeal-'): continue
                    await thread.edit(locked=True)
                    await thread.send(f'User {ticket.suspect.mention} has been suspended.')
                except:
                    pass
        update_ticket_firebase(ticket.mod_thread_id, ticket)            

    async def reject_callback(interaction: discord.Interaction):
        if not ticket.claimed: return

        await interaction.response.defer()
        
        ticket.action_state = TicketActionState.ACTION_REJECTED
        await ticket.complete_report()

        await interaction.followup.send(f'Ticket marked as false report by {interaction.user}.')  
        update_ticket_firebase(ticket.mod_thread_id, ticket)           

    async def create_thread_callback(interaction: discord.Interaction):
        if not ticket.claimed or ticket.reporter_thread: return

        await interaction.response.defer()

        await ticket.create_reporter_thread(client)
        claimed_view.disable_create_thread_button()
        ticket.claimed_webhook_message = await ticket.claimed_webhook_message.edit(view=claimed_view.view())
        await interaction.followup.send(f'Created private thread with reporter: {ticket.reporter_thread.mention}')
        update_ticket_firebase(ticket.mod_thread_id, ticket)

    unclaimed_view.claim_button.callback = claim_callback
    claimed_view.set_callbacks(create_thread_callback, accept_callback, reject_callback, unclaim_callback) 

    if ticket.ai_score and ticket.ai_score >= 90:
        ticket.set_claimed(client.user)
        unclaimed_view.disable_claim_button()
        await ticket.main_message.edit(content=ticket.main_content(), view=unclaimed_view.view())
        await ticket.mod_thread.send(f'Ticket claimed by {client.user}.')  
        
        ticket.action_state = TicketActionState.ACTION_ACCEPTED
        await ticket.complete_report()

        category_id = ticket.category_id
        interaction_message, reporter_message, suspect_message, action = accept_report_workflow(ticket)

        await ticket.mod_thread.send(interaction_message)
        await ticket.suspect.send(suspect_message)
        await ticket.suspect.send(f'If this is a mistake, please type `appeal {ticket.mod_thread_id}`.')

        bad_user = client.bad_users[ticket.suspect.id]
        bad_user[ticket.mod_thread_id] = ticket
        if action == 'warn':
            bad_user['state'] = BadUserState.WARN
        else:
            bad_user['state'] = BadUserState.SUSPEND
            for thread in client.main_channel.threads:
                try:
                    await thread.fetch_member(ticket.suspect.id)
                    if thread.name.startswith('appeal-'): continue
                    await thread.edit(locked=True)
                    await thread.send(f'User {ticket.suspect.mention} has been suspended.')
                except:
                    pass    
        update_ticket_firebase(ticket.mod_thread_id, ticket)        

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

    if not reported_user_information and is_debug():
        reported_user_information = {
            'num_report': 1,
            'warned': 2,
            'last_report': None,
        }
    return report_information, reported_user_information