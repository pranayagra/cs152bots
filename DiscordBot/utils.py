import discord
from discord.utils import get
from discord.ext import commands
from enum import Enum, auto
import re
from bs4 import BeautifulSoup
from bs4.element import Comment
import urllib.request

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

class BadUserState(Enum):
    SUSPEND = auto()
    WARN = auto()
    NONE = auto()


def ai_links(message):
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
