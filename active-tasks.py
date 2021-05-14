from jira import JIRA

import config
from config import logger, email
from structures import Issue


JIRA_PROJECT = 'SYSINFR'

logger.add(sink=config.LOG_DIR / 'active-tasks.log',
           rotation=config.SETTINGS['logging']['rotation'],
           format=config.SETTINGS['logging']['format'],
           level='INFO')


@logger.catch
def main():
    jira = JIRA(**config.JIRA)
    jql = (f'project = {JIRA_PROJECT} AND type = "Backup & Restore" AND '
           f'status NOT IN (Closed, Rejected, Resolved)')

    opened_issues = []
    for issue in jira.search_issues(jql, maxResults=False):
        comments = jira.comments(issue)
        opened_issues.append(Issue(issue, comments))

    if opened_issues:
        subject = f'JIRA ({JIRA_PROJECT}) | Active tasks'
        body = config.SYSINFR_TEMPLATE.render(project=JIRA_PROJECT,
                                              issues=opened_issues,
                                              wiki=config.SETTINGS['wiki'])
        email.notify(subject=subject, message=body)
        logger.info(f'{len(opened_issues)} tasks are found')
    else:
        logger.info('nothing is found')


if __name__ == '__main__':
    main()
