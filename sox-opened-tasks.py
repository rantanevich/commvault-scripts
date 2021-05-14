import re
from datetime import datetime
from collections import defaultdict

from jira import JIRA

import config
from config import logger, email


JIRA_PROJECT = 'SOX'
LOOKUP_DAYS = 7

logger.add(sink=config.LOG_DIR / 'sox-opened-tasks.log',
           rotation=config.SETTINGS['logging']['rotation'],
           format=config.SETTINGS['logging']['format'],
           level='INFO')


@logger.catch
def main():
    jira = JIRA(**config.JIRA)
    jql = (f'project={JIRA_PROJECT} AND summary ~ JobSummary AND status = Open '
           f'AND created > startOfDay(-{LOOKUP_DAYS}) AND created < now() '
           f'ORDER BY key DESC')

    opened_issues = defaultdict(list)
    for issue in jira.search_issues(jql, maxResults=False):
        services = (config.SETTINGS['sox_services'] +
                    config.SETTINGS['admin_services'])
        for service_name in services:
            if service_name in issue.fields.summary:
                username = issue.fields.assignee.name
                domain = config.SETTINGS['smtp']['domain']
                email_address = f'{username}@{domain}'
                issue.fields.summary = service_name
                break
        else:
            logger.error(f'there is unknown service ({issue.fields.summary})')


        created_date = datetime.strptime(issue.fields.created,
                                         '%Y-%m-%dT%H:%M:%S.000%z')
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

        opened_issues[email_address].append({
            'key': issue.key,
            'created': created_date,
            'summary': issue.fields.summary,
            'assignee': issue.fields.assignee.displayName,
            'reporter': issue.fields.reporter.displayName,
            'status': issue.fields.status.name,
            'comments': comments,
            'href': f'{config.SETTINGS["jira"]}/browse/{issue.key}'
        })

    for email_address, issues in opened_issues.items():
        subject = f'{issues[0]["summary"]} | Backup monitoring'
        body = config.SOX_TEMPLATE.render(project=JIRA_PROJECT,
                                          issues=issues,
                                          wiki=config.SETTINGS['wiki'])
        email.notify(subject=subject, message=body)
        logger.info(f'{len(opened_issues)} tasks are found')

    if not opened_issues:
        logger.info('Nothing is found')


if __name__ == '__main__':
    main()
