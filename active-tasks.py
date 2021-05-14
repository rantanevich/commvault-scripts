import re
from datetime import datetime

from jira import JIRA

import config
from config import logger, email


JIRA_PROJECT = 'SYSINFR'

logger.add(sink=config.LOG_DIR / 'active-sysinfr-tasks.log',
           rotation=config.SETTINGS['logging']['rotation'],
           format=config.SETTINGS['logging']['format'],
           level='INFO')


@logger.catch
def main():
    jira = JIRA(**config.JIRA)
    jql = (f'project = {JIRA_PROJECT} and type = "Backup & Restore" and '
           f'status not in (Closed, Rejected, Resolved)')

    opened_issues = []
    for issue in jira.search_issues(jql, maxResults=False):
        created_date = datetime.strptime(issue.fields.created, '%Y-%m-%dT%T.000%z')
        created_date = created_date.strftime('%d.%m.%Y')

        comments = []
        for comment in jira.comments(issue):
            comment.body = comment.body.replace('\r\n', ' ')
            comment.body = comment.body.replace('\n', ' ')
            comment.body = re.sub('{.+?}', '', comment.body)
            comment.body = re.sub('\\xa0', ' ', comment.body)

            if hasattr(comment, 'author'):
                if comment.author.displayName == 'A1 JIRA': continue
                message = f'({comment.author.displayName}): {comment.body}'
            else:
                message = f'(Anonymous): {comment.body}'
            comments.append(message)

        opened_issues.append({
            'key': issue.key,
            'created': created_date,
            'summary': issue.fields.summary,
            'assignee': issue.fields.assignee.displayName,
            'reporter': issue.fields.reporter.displayName,
            'status': issue.fields.status.name,
            'comments': comments,
            'href': f'{config.SETTINGS["jira"]}/browse/{issue.key}'
        })

    if opened_issues:
        subject = f'JIRA ({JIRA_PROJECT}) | Active tasks'
        body = config.SYSINFR_TEMPLATE.render(project=JIRA_PROJECT,
                                              issues=opened_issues,
                                              wiki=config.SETTINGS['wiki'])
        email.notify(subject=subject, message=body)
        logger.info(f'{len(opened_issues)} tasks are found')
    else:
        logger.info('Nothing is found')


if __name__ == '__main__':
    main()
