#!/usr/bin/env python3
import os
import urllib3
from pathlib import Path
from functools import partial

import yaml
from dotenv import load_dotenv
from jinja2 import Template
from loguru import logger
from notifiers import get_notifier
from notifiers.logging import NotificationHandler


load_dotenv()

# disable InsecureRequestWarning
urllib3.disable_warnings()

BASE_DIR = Path(__file__).parent

LOG_DIR = BASE_DIR / 'logs'
LOG_DIR.mkdir(exist_ok=True)

SETTINGS_FILE = BASE_DIR / 'settings.yml'
SETTINGS = yaml.safe_load(SETTINGS_FILE.open())

SOX_TEMPLATE_FILE = BASE_DIR / 'templates' / 'sox.html.j2'
SOX_TEMPLATE = Template(SOX_TEMPLATE_FILE.read_text(encoding='utf8'))

SYSINFR_TEMPLATE_FILE = BASE_DIR / 'templates' / 'sysinfr.html.j2'
SYSINFR_TEMPLATE = Template(SOX_TEMPLATE_FILE.read_text(encoding='utf8'))

JIRA = {
    'server': SETTINGS['jira'],
    'basic_auth': (os.getenv('JIRA_USERNAME'), os.getenv('JIRA_PASSWORD')),
    'options': {'verify': False},
}

COMMVAULT = {
    'webconsole_hostname': SETTINGS['commvault']['api'],
    'commcell_username': os.getenv('COMMVAULT_USERNAME'),
    'commcell_password': os.getenv('COMMVAULT_PASSWORD'),
}

SMTP_PARAMS = {
    'from': SETTINGS['smtp']['from'],
    'to': SETTINGS['smtp']['to'],
    'subject': 'Commvault | Automation scripts',
    'host': SETTINGS['smtp']['host'],
    'port': SETTINGS['smtp']['port'],
    'tls': SETTINGS['smtp']['tls'],
    'username': os.getenv('SMTP_USERNAME'),
    'password': os.getenv('SMTP_PASSWORD'),
    'html': SETTINGS['smtp']['html'],
}

email = get_notifier('email')
email.notify = partial(email.notify, **SMTP_PARAMS)

logger.remove()
logger.add(sink=NotificationHandler('email', defaults=SMTP_PARAMS),
           format=SETTINGS['logging']['format'],
           level='ERROR')
