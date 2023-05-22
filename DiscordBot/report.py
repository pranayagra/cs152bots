from enum import Enum, auto
import discord
import re
import numpy as np
import os.path
from datetime import date
import pickle as pkl

# class PersistentInformation:
#     def __init__(self):
#         self.all_report_information = {}

#     def add_ticket(self, suspect, ticket_id, ticket_information):
#         if suspect.id not in self.all_report_information:
#             self.all_report_information[suspect.id] = {}
        
#         suspect_report_information = self.all_report_information[suspect.id]

#         if ticket_id not in suspect_report_information:
#             suspect_report_information[ticket_id] = {}
        
#         suspect_ticket_information = suspect_report_information[ticket_id]

#         suspect_ticket_information['reporter'] = ticket_information['reporter']
#         suspect_ticket_information['reason'] = ticket_information['reason']
#         suspect_ticket_information['state'] = ticket_information['state']
#         suspect_ticket_information['date'] = ticket_information['date']
#         suspect_ticket_information['mod_action'] = ticket_information['mod_action']
#         suspect_ticket_information['appeal'] = ticket_information['appeal']

#     def num_reports(self, suspect):
#         if suspect.id not in self.all_report_information:
#             return 0
#         return len(self.all_report_information[suspect.id])

#     # user.id => {ticket.id: {}, ticket.id: {}}
#     def save_user_information(self, user_id, user_name, user_discriminator, user_avatar):

class State(Enum):
    REPORT_START = auto()
    AWAITING_MESSAGE = auto()
    MESSAGE_IDENTIFIED = auto()
    REPORT_COMPLETE = auto()

class Report:
    START_KEYWORD = "report"
    CANCEL_KEYWORD = "cancel"
    HELP_KEYWORD = "help"

    def __init__(self, client):
        self.state = State.REPORT_START
        self.client = client
        self.message = None
        self.report_type = []
        self.report_content = {}
        self.build_report_type()
        self.reason = []
        self.log = {}
        self.read_user_information()
        self.cancel = False
    
    def read_user_information(self):
        if os.path.exists('reported_user_info.pkl'):
            with open('reported_user_info.pkl', 'rb') as handle:
                self.reported_user_information = pkl.load(handle)
        else:
            self.reported_user_information = {}

    def build_report_type(self):
        self.report_content['Spam'] = [['Please select the type of spam', 
                                    'Excessive repeated messages', 
                                    'Advertising unwanted goods', 
                                    'Promoting sex work(OnlyFans, prostitution, etc)']]
        self.report_content['Harassment'] = [['Please select the type of harassment',
                                          'Sexual Harassment',
                                          'Racism',
                                          'Hate Speech']]
        self.report_content['Scam/Catfishing'] = [['Please select the type of scam/catfishing',
                                                'This person is a bot',
                                                'This person is pretending to be someone else',
                                                'I think this user is a minor',
                                                'This person is trying to get money from me (ex. asking for Venmo, CashApp)'],
                                                ['This person is...',
                                                'Pretending to be me or my friend',
                                                'Pretending to be a public figure'],
                                                ['Please select why you believe this user is a minor',
                                                'This user\'s bio or messages said they are a minor',
                                                'other: [write in text box]']
                                               ]
        self.report_content['Imminent Danger'] = [['Please select the type of danger',
                                                'Credible threat of violence',
                                                'Self-harm or suicidal intent']]
        self.report_content['Illegal or inappropriate content'] = [['Please select the type of content',
                                                                 'Adult nudity',
                                                                 'Child sexual abuse material',
                                                                 'Depiction of violence',
                                                                 'Images of weapons',
                                                                 'Images of drugs']]
        self.report_type = list(self.report_content.keys())
    
    
    async def handle_message(self, message):
        '''
        This function makes up the meat of the user-side reporting flow. It defines how we transition between states and what 
        prompts to offer at each of those states. You're welcome to change anything you want; this skeleton is just here to
        get you started and give you a model for working with Discord. 
        '''

        if message.content == self.CANCEL_KEYWORD:
            self.state = State.REPORT_COMPLETE
            self.cancel = True
            return ["Report cancelled."]
        
        if self.state == State.REPORT_START:
            reply =  "Thank you for starting the reporting process. "
            reply += "Say `help` at any time for more information.\n\n"
            reply += "Please copy paste the link to the message you want to report.\n"
            reply += "You can obtain this link by right-clicking the message and clicking `Copy Message Link`."
            self.state = State.AWAITING_MESSAGE
            return [reply]
        
        if self.state == State.AWAITING_MESSAGE:
            # Parse out the three ID strings from the message link
            link = message.content
            m = re.search('/(\d+)/(\d+)/(\d+)', link)
            if not m:
                return ["I'm sorry, I couldn't read that link. Please try again or say `cancel` to cancel."]
            guild = self.client.get_guild(int(m.group(1)))
            if not guild:
                return ["I cannot accept reports of messages from guilds that I'm not in. Please have the guild owner add me to the guild and try again."]
            
            thread = self.client.main_channel.get_thread(int(m.group(2)))
            if not thread:
                return ["It seems this thread was deleted or never existed. Please try again or say `cancel` to cancel."]
            try:
                message = await thread.fetch_message(int(m.group(3)))
            except discord.errors.NotFound:
                return ["It seems this message was deleted or never existed. Please try again or say `cancel` to cancel."]

            # Here we've found the message - it's up to you to decide what to do next!
            self.state = State.MESSAGE_IDENTIFIED
            reply = ["I found this message:", "```" + message.author.name + ": " + message.content + "```", \
                    "Please select the reason for reporting this user/this message(1-5): \n"]
            self.log['reported_user'] = message.author
            self.log['reported_message'] = message.content
            self.log['reported_thread'] = thread.name
            self.log['reported_url'] = link
            self.log['severity'] = 'Medium'
            # self.log['thread_id'] = thread.id
            for i, reason in enumerate(self.report_type):
                reply[-1] += (str(i+1) + '. '+ reason+'\n')
            return reply
        
        if self.state == State.MESSAGE_IDENTIFIED:
            if self.reason == []:
                if message.content in ['1','2','3','4','5']:
                    self.log['user'] = message.author
                    self.reason.append(message.content)
                    self.log['reason'] = [self.report_type[int(message.content)-1]]
                    self.log['reported_category'] = self.report_type[int(message.content)-1]
                    steps = self.report_content[self.report_type[int(message.content)-1]][0]
                    reply = ''
                    for index in range(len(steps)):
                        if index == 0:
                            reply += (steps[0]+':\n')
                        else:
                            reply += (str(index) + '. '+ steps[index]+'\n')
                    return [reply]
                else:
                    # self.state = State.REPORT_COMPLETE
                    return ["Please select the reason for reporting this user/this message(1-5)"]
            elif self.reason[0] == '3':
                self.log['severity'] = 'High'
                if len(self.reason) == 1 and message.content in ['2','3']:
                    self.reason.append(int(message.content))
                    # self.log['reason'].append(self.report_content['Scam/Catfishing'][int(message.content)-1][0])
                    steps = self.report_content[self.report_type[int(self.reason[0])-1]][int(message.content)-1]
                    reply = ''
                    for index in range(len(steps)):
                        if index == 0:
                            reply += (steps[0]+':\n')
                        else:
                            reply += (str(index) + '. '+ steps[index]+'\n')
                    return [reply]
                elif len(self.reason) == 2 and self.reason[-1] == 3 and '2' in message.content:
                    self.reason.append(2)
                    text_box = message.content[2:]
                    self.log['reason'].append(text_box)
                    reply = "Your report is recorded with reason: "
                    for reason in self.log['reason']:
                        reply += (reason +' -- ')
                    reply = reply[:-4]
                    self.record_and_complete()
                    return [reply]
                else:
                    self.reason.append(int(message.content))
                    if self.reason[1] in [2, 3]:
                        self.log['reason'].append(self.report_content['Scam/Catfishing'][self.reason[1]-1][int(message.content)])
                    else:
                        self.log['reason'].append(self.report_content['Scam/Catfishing'][0][int(message.content)])
                    reply = "Your report is recorded with reason: "
                    for reason in self.log['reason']:
                        reply += (reason +' -- ')
                    reply = reply[:-4]
                    self.record_and_complete()
                    return [reply]
            else:
                self.log['reason'].append(self.report_content[self.log['reason'][0]][0][int(message.content)])
                reply = "Your report is recorded with reason: "
                for reason in self.log['reason']:
                    reply += (reason +' -- ')
                reply = reply[:-4]
                self.record_and_complete()
                return [reply]

        return []

    def record_and_complete(self):
        # print(self.log['reported_user'].id, type(self.log['reported_user'].id))
        if self.log['reported_user'].id not in self.reported_user_information:
            self.reported_user_information[self.log['reported_user'].id] = {}
            self.reported_user_information[self.log['reported_user'].id]['num_report'] = 0
            self.reported_user_information[self.log['reported_user'].id]['warned'] = 0
        self.reported_user_information[self.log['reported_user'].id]['last_report'] = None
        self.reported_user_information[self.log['reported_user'].id]['num_report'] +=1
        self.reported_user_information[self.log['reported_user'].id]['warned'] +=1
        self.reported_user_information[self.log['reported_user'].id]['last_report'] = date.today()

        print(self.reported_user_information)
        with open('reported_user_info.pkl', 'wb') as handle:
            pkl.dump(self.reported_user_information, handle)
        # np.save('reported_user_info.npy', self.reported_user_information)
        self.state = State.REPORT_COMPLETE

    
    def report_complete(self):
        return self.state == State.REPORT_COMPLETE
    


    

