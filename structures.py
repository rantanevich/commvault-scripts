import re
from datetime import datetime

from config import SETTINGS


class Issue:
    def __init__(self, issue, comments):
        self.key = issue.key
        self.created = self._parse_created(issue.fields.created)
        self.summary = issue.fields.summary
        self.assignee = issue.fields.assignee.displayName
        self.reporter = issue.fields.reporter.displayName
        self.status = issue.fields.status.name
        self.comments = self._parse_comments(comments)
        self.href = f'{SETTINGS["jira"]}/browse/{issue.key}'

    def _parse_created(self, created):
        date = datetime.strptime(created, '%Y-%m-%dT%H:%M:%S.000%z')
        return date.strftime('%d.%m.%Y')

    def _parse_comments(self, comments):
        items = []
        for comment in comments:
            comment.body = comment.body.replace('\r\n', ' ')
            comment.body = comment.body.replace('\n', ' ')
            comment.body = re.sub('{.+?}', '', comment.body)
            comment.body = re.sub('\\xa0', ' ', comment.body)

            if hasattr(comment, 'author'):
                if comment.author.displayName == 'A1 JIRA': continue
                message = f'({comment.author.displayName}): {comment.body}'
            else:
                message = f'(Anonymous): {comment.body}'
            items.append(message)
        return items
