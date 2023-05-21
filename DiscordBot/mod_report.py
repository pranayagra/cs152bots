import discord
from discord import app_commands, utils
from discord.ext import commands
from discord.ui import Button, View
from discord.utils import get
from enum import Enum, auto


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
        false_report_button = Button(style=discord.ButtonStyle.red, label='False Report')
        create_thread_button = Button(style=discord.ButtonStyle.blue, label='Create Reporter Thread')
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

class TicketState(Enum):
    REPORT_UNCLAIMED = auto()
    REPORT_CLAIMED = auto()
    REPORT_COMPLETE = auto()
    REPORT_APPEAL = auto()

class Ticket:
    def __init__(self, report_information, reported_user_information, mod_channel):
        self.report_information = report_information
        self.reported_user_information = reported_user_information

        self.mod_channel = mod_channel

        self.main_message = None
        self.main_message_text = format_ticket_message(report_information)

        self.reporter = report_information['user']
        self.suspect = report_information['reported_user']

        self.state = TicketState.REPORT_UNCLAIMED

        self.claimed = False
        self.claimed_by = None
        self.claimed_webhook_message = None
        
        self.mod_thread = None
        self.reporter_thread = None

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

# class TicketDisplay:
#     def __init__(self, ticket):
#         self.ticket = ticket
#         self.ticket_view = None

#     def create_ticket_view(self):
#         self.ticket_view = TicketView(self.ticket)
#         return self.ticket_view

def new_report_prepend():
    return f'New report ticket! Click the Claim button to claim the ticket.\n'

def claimed_report_prepend(claimer):
    return f'This ticket has been claimed by {claimer.mention}.\n'

def format_ticket_message(report_information):
    return f"""
    **Severity**: {report_information['severity']}
    **User**: {report_information['user']}
    **Reported User**: {report_information['reported_user']}

    **Category**: {report_information['reported_category']}
    **Reason**: {report_information['reason']}
    **Message**: ```{report_information['reported_message']}```
    **Channel**: {report_information['reported_channel']}
    **Link**: {report_information['reported_url']}

    **AI Score**: {report_information['reported_score']}
    """

