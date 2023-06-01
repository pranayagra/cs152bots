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

Message: %s''' % (reporting_categories[0], reporting_categories[1], reporting_categories[2], reporting_categories[3], message)
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

Message: %s''' % (reporting_categories[category-1], message)
    response = openai.ChatCompletion.create(
        model="gpt-3.5-turbo",
        messages=[
                {"role": "system", "content": "You are a helpful assistant for trust and safety engineering on a dating app"},
                {"role": "user", "content": prompt + message},
            ]
    )
    score = response['choices'][0]['message']['content']
    score = re.findall(r'\d+', score)
    if score:
        return score[-1]
    else:
        50

class BadUserState(Enum):
    SUSPEND = auto()
    WARN = auto()
    NONE = auto()


def has_bad_links(message):
    urls = text_to_urls(message.content)
    for url in urls:
        try:
            text = url_to_text(url)
            if text is None: continue
            # use AI to categorize text

        except:
            pass
            
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

if __name__ == '__main__':
    # msg = 'im a bot'
    # msg = 'im am 19 yrs old'
    # msg = 'pay me 100 on Venmo'
    msg = 'my mom needs money'
    cat = message_autoflag(msg)
    print(cat)
    score = ai_score(msg, cat)
    print(score)
