import discord
from discord.utils import get
from discord.ext import commands
from enum import Enum, auto
import re
from bs4 import BeautifulSoup
from bs4.element import Comment
import urllib.request
import openai
import os
import json
import requests
from unidecode import unidecode
import firebase_admin
from firebase_admin import credentials
from firebase_admin import firestore


# Use a global variable to store the Firebase app instance
if not firebase_admin._apps:
    cred = credentials.Certificate('cs152-30e28-firebase-adminsdk-a4oyb-711a91d46d.json')
    firebase_admin.initialize_app(cred)
db = firestore.client()

token_path = 'tokens.json'
if not os.path.isfile(token_path):
    raise Exception(f"{token_path} not found!")
with open(token_path) as f:
    # If you get an error here, it means your token is formatted incorrectly. Did you put it in quotes?
    tokens = json.load(f)
    discord_token = tokens['discord']
    openai.organization = tokens['openai.organization']
    openai.api_key = tokens['openai.api_key']

DEBUG = True

def is_debug():
    return DEBUG

async def check_issue(condition, func, message):
    if condition: 
        await func(message)
        return True
    return False

def get_category_by_name(guild, category_name):
    for category in guild.categories:
        if category.name == category_name:
            return category
    return None

reporting_categories = [
    'user is a bot',
    'user is pretending to be someone else',
    'user is a minor',
    'user is trying to get money (eg. asking for Venmo, CashApp)',
]

def message_autoflag(message):
    prompt = \
'''Pick a number 1-5 for the following categories. Do not respond with anything else.
1. %s
2. %s
3. %s
4. %s
5. none

Message: %s
Number: ''' % (reporting_categories[0], reporting_categories[1], reporting_categories[2], reporting_categories[3], message)
    response = openai.ChatCompletion.create(
        model="gpt-3.5-turbo",
        messages=[
                {"role": "system", "content": "You are a helpful assistant for trust and safety engineering on a dating app"},
                {"role": "user", "content": prompt},
            ]
    )
    category_response = response['choices'][0]['message']['content']
    for i in range(1, 6):
        if f'{i}' in category_response:
            return i
    return 5

def ai_score(message, category):
    assert category in [1, 2, 3, 4]
    prompt = \
'''With what probability does the below message from a user indicate that %s?
Pick a number 0-100. Do not respond with anything else.

Message: %s
Score: ''' % (reporting_categories[category-1], message)
    response = openai.ChatCompletion.create(
        model="gpt-3.5-turbo",
        messages=[
                {"role": "system", "content": "You are a helpful assistant for trust and safety engineering on a dating app"},
                {"role": "user", "content": prompt},
            ]
    )
    score = response['choices'][0]['message']['content']
    print('AI SCORE RAW: ', score)
    score = re.findall(r'\d+', score)
    if score:
        return int(score[-1])
    else:
        50

class BadUserState(Enum):
    SUSPEND = auto()
    WARN = auto()
    NONE = auto()


def has_bad_links(message):
    urls = text_to_urls(message)
    for url in urls:
        try:
            text = url_to_text(url)
            if text is None: continue
            # use AI to categorize text
            prompt = \
'''Does the below message fall into any of the below categories:
1. Spam
2. Harassment
3. Scam/catfishing
4. Imminent danger
5. Illegal or inappropriate content

Message: %s

Answer yes/no. Do not respond with anything else.''' % (message)
            response = openai.ChatCompletion.create(
                model="gpt-3.5-turbo",
                messages=[
                        {"role": "system", "content": "You are a helpful assistant for trust and safety engineering on a dating app"},
                        {"role": "user", "content": prompt},
                    ]
            )
            response = response['choices'][0]['message']['content']
            print(response)
            if 'yes' in response.lower():
                return 1

        except:
            pass
    return 0
            
def tag_visible(element):
    if element.parent.name in ['style', 'script', 'head', 'title', 'meta', '[document]']:
        return False
    if isinstance(element, Comment):
        return False
    return True

def text_from_html(body):
    soup = BeautifulSoup(body, 'html.parser')
    texts = soup.findAll(text=True)
    visible_texts = filter(tag_visible, texts)  
    return u" ".join(t.strip() for t in visible_texts)

def text_to_urls(text):
    return re.findall(r"(https?://\S+)", text)

def url_to_text(url):
    try:
        html = urllib.request.urlopen(url).read()
        return text_from_html(html)
    except:
        pass

def replace_unicode_from_text(text):
    try:
        return unidecode(text)
    except:
        return text

# Firebase Functions

def update_ticket_firebase(ticket_id, ticket):
    '''
    updates (or creates) key ticket_id with value as ticket to firebase database, or adds to firebase database if it does not exist
    ticket_id: int
    ticket: class Ticket
    '''
    db.collection('all_tickets').document(str(ticket_id)).set(ticket.to_dict(), merge=True)

def create_user_data_in_firebase(user_id, user_data):
    '''
    adds user_data to firebase database with user_id as key
    Current Structure:
    Collection("users").document(user_id).collection("data").document("userData")
    '''
    db.collection('users').document(str(user_id)).collection('data').document('userData').set(user_data.to_dict())
    return

# TODO(Pranay): to use this function
def update_user_data_in_firebase(user_id, user_data):
    '''
    updates user_data in firebase database with user_id as key
    Current Structure:
    Collection("users").document(user_id).collection("data").document("userData")
    '''
    db.collection('users').document(str(user_id)).collection('data').document('userData').set(user_data.to_dict(), merge=True)
   

def get_user_data_firebase(user_id):
    '''
    returns user data for user_id from firebase database
    user_id: int
    returns: dictionary for user_id with data [username, num_warnings, num_suspends, num_reports_made, num_reports_against, is_banned, is_verified_account]
    '''
    doc = db.collection('users').document(str(user_id)).collection('data').document('userData').get()
    if doc.exists:
        return doc.to_dict()
    else:
        print("user does not exist")
        return {}

def add_match_request_firebase(user_id1, user_id2):
    '''
    adds a match request to firebase database
    user_id1: int
    user_id2: int
    '''
    # Create a reference to the matches documents for both users
    doc_ref1 = db.collection('users').document(str(user_id1)).collection('data').document('matches')
    doc_ref2 = db.collection('users').document(str(user_id2)).collection('data').document('matches')

    # Get the current state of the matches documents
    doc1 = doc_ref1.get()
    doc2 = doc_ref2.get()

    if doc1.exists:
        # If the matches document exists for user_id1, append user_id2
        doc_ref1.update({'matched_ids': firestore.ArrayUnion([user_id2])})
    else:
        # If the matches document does not exist for user_id1, create it with user_id2
        doc_ref1.set({'matched_ids': [user_id2]})

    if doc2.exists:
        # If the matches document exists for user_id2, append user_id1
        doc_ref2.update({'matched_ids': firestore.ArrayUnion([user_id1])})
    else:
        # If the matches document does not exist for user_id2, create it with user_id1
        doc_ref2.set({'matched_ids': [user_id1]})

def remove_match_request_firebase(user_id1, user_id2):
    '''
    removes a match request from firebase database
    user_id1: int
    user_id2: int
    '''
    # Create a reference to the matches documents for both users
    doc_ref1 = db.collection('users').document(str(user_id1)).collection('data').document('matches')
    doc_ref2 = db.collection('users').document(str(user_id2)).collection('data').document('matches')

    # Get the current state of the matches documents
    doc1 = doc_ref1.get()
    doc2 = doc_ref2.get()

    if doc1.exists and user_id2 in doc1.get('matched_ids'):
        # If the matches document exists for user_id1 and user_id2 is in the list of matches, remove user_id2
        doc_ref1.update({'matched_ids': firestore.ArrayRemove([user_id2])})

    if doc2.exists and user_id1 in doc2.get('matched_ids'):
        # If the matches document exists for user_id2 and user_id1 is in the list of matches, remove user_id1
        doc_ref2.update({'matched_ids': firestore.ArrayRemove([user_id1])})

VALID_ATTRIBUTES = {'username', 'user_id', 'num_warnings', 'num_suspends', 'num_reports_made', 'num_reports_against', 'is_banned', 'is_verified_account'}

def get_user_attribute_firebase(user_id, attribute):
    '''
    returns specific attribute from user data for user_id from firebase database
    user_id: int
    attribute: str
    returns: the attribute value for user_id
    '''
    if attribute not in VALID_ATTRIBUTES:
        raise ValueError(f"Invalid attribute: {attribute}")
    user_data = db.collection('users').document(str(user_id)).collection('data').document('userData').get()
    if user_data.exists:
        return user_data.get(attribute)
    else:
        return None

def update_user_attribute_firebase(user_id, attribute, value=None, increment=False, decrement=False):
    '''
    updates specific attribute in user data for user_id in firebase database
    user_id: int
    attribute: str
    value: value to set or increment/decrement by
    increment: boolean, if True increment attribute value
    decrement: boolean, if True decrement attribute value
    '''
    if attribute not in VALID_ATTRIBUTES:
        raise ValueError(f"Invalid attribute: {attribute}")
    user_ref = db.collection('users').document(str(user_id)).collection('data').document('userData')
    if increment:
        user_ref.update({attribute: firestore.Increment(1)})
    elif decrement:
        user_ref.update({attribute: firestore.Increment(-1)})
    elif value:
        user_ref.update({attribute: value})
    else:
        raise ValueError(f"Please specify value, increment, or decrement")
    return

# usage examples
# update_user_attribute_firebase(user_id='123', attribute='num_warnings', value=1, increment=True)
# update_user_attribute_firebase(user_id='123', attribute='is_banned', value=True)

# Regex banned words TODO(yih301): utilize
def fetch_banned_words():
    doc_ref = db.collection("general_data").document("banned")
    doc = doc_ref.get()
    if doc.exists:
        return doc.to_dict().get('banned_words', [])
    else:
        return []
    
def add_banned_word(word):
    doc_ref = db.collection("general_data").document("banned")
    doc = doc_ref.get()
    if doc.exists:
        doc_ref.update({'banned_words': firestore.ArrayUnion([word])})
    else:
        doc_ref.set({'banned_words': [word]})

def remove_banned_word(word):
    doc_ref = db.collection("general_data").document("banned")
    doc = doc_ref.get()
    if doc.exists:
        doc_ref.update({'banned_words': firestore.ArrayRemove([word])})


if __name__ == "__main__":
    # to test database functions
    new_user_data = get_user_data_firebase('1024354403773329541')
    print(new_user_data)
    update_user_attribute_firebase('1024354403773329541', 'num_warnings', increment=True)
    print(get_user_attribute_firebase('1024354403773329541', 'num_warnings'))