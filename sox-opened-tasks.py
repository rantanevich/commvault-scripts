from collections import defaultdict

from jira import JIRA

import config
from config import logger, email
from structures import Issue


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
                assignee = issue.fields.assignee.name
                email_domain = config.SETTINGS['smtp']['domain']
                email_address = f'{assignee}@{email_domain}'
                issue.fields.summary = service_name
                break
        else:
            logger.error(f'there is unknown service ({issue.fields.summary})')
            continue

        comments = jira.comments(issue)
        opened_issues[email_address].append(Issue(issue, comments))

    for email_address, issues in opened_issues.items():
        subject = f'{issues[0]["summary"]} | Backup monitoring'
        body = config.SOX_TEMPLATE.render(project=JIRA_PROJECT,
                                          issues=issues,
                                          wiki=config.SETTINGS['wiki'])
        recipients = config.SMTP_PARAMS['to'] + [email_address]
        email.notify(subject=subject, to=recipients, message=body)
        logger.info(f'{len(opened_issues)} tasks are found')

    if not opened_issues:
        logger.info('nothing is found')


if __name__ == '__main__':
    main()
