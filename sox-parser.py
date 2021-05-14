import re

from jira import JIRA
from cvpysdk.commcell import Commcell
from cvpysdk.clientgroup import ClientGroup
from cvpysdk.job import JobController

import config
from config import logger


logger.add(sink=config.LOG_DIR / 'sox-parser.log',
           rotation=config.SETTINGS['logging']['rotation'],
           format=config.SETTINGS['logging']['format'],
           level='INFO')


@logger.catch
def main():
    jira = JIRA(**config.JIRA)
    commvault = Commcell(**config.COMMVAULT)
    job_controller = JobController(commvault)

    for service_name in config.SETTINGS['sox_services']:
        client_group = ClientGroup(commvault, service_name)
        clients = client_group.associated_clients

        issues = []
        for client_name in clients:
            jobs = job_controller.all_jobs(
                client_name=client_name,
                job_summary='full',
                limit=config.SETTINGS['commvault']['jobs_limit'],
                lookup_time=config.SETTINGS['commvault']['lookup_time'],
            )
            for job_id in jobs:
                job = jobs[job_id]
                job_status = job['status'].lower()
                job_failed_files = job['totalFailedFiles']
                job_failed_folders = job['totalFailedFolders']

                if (job_status == 'completed' and (
                        not (job_failed_files or job_failed_folders) or
                        job['appTypeName'] == 'Virtual Server')):
                    continue

                issue = {
                    'job_id': job_id,
                    'client': client_name,
                    'status': job_status,
                    'percent': job['percentComplete'],
                    'reason': '',
                    'comment': '',
                }
                logger.info(f'client={issue["client"]} '
                            f'job_id={issue["job_id"]} '
                            f'status={issue["status"]} '
                            f'failed_files={job_failed_files} '
                            f'failed_folders={job_failed_folders}')

                if job_status in ['running', 'waiting']:
                    message = f'Progress: {job["percentComplete"]}%'
                    issue['comment'] = make_comment(issue, message)

                elif job_status in ['pending', 'failed', 'killed',
                                    'suspended', 'failed to start']:
                    issue['reason'] = job['pendingReason']
                    pattern = 'backup activity for subclient .+ is disabled'
                    if re.match(pattern, issue['reason'], flags=re.IGNORECASE):
                        issue['reason'] = ('Backup activity for subclient '
                                           'is disabled')

                elif (job_status == 'completed' and
                        (job_failed_files or job_failed_folders)):
                    issue['reason'] = (f'Failed to back up: '
                                       f'{job_failed_folders} Folders, ',
                                       f'{job_failed_files} Files')

                elif (job['appTypeName'] == 'Virtual Server' and
                        job_status == 'completed w/ one or more errors'):
                    issue['reason'] = job_status
                    job_detail = job_controller.get(job_id).details['jobDetail']
                    vms = job_detail['clientStatusInfo']['vmStatus']

                    # After restoring VM with new name, Commvault renames old client name
                    # For example, src: srv-tibload-001, dest: srv-tibload-001_20102020
                    client_vm_name = client_name.split('_')[0]

                    vm_found = False
                    for vm in vms:
                        if vm['vmName'].startswith(client_vm_name):
                            vm_found = True
                            issue['reason'] = vm['FailureReason']
                            break

                    if not vm_found:
                        logger.error(f'{client_vm_name} is not found '
                                     f'in the job ({job_id})')

                elif job_status == 'completed w/ one or more errors':
                    issue['reason'] = job['pendingReason']

                elif job_status == 'committed':
                    issue['reason'] = ('Job was cancelled, but '
                                       'some items successfully backed up')

                else:
                    logger.error(f'undefined job: {job}')

                if issue['reason'] and not issue['comment']:
                    for error in config.SETTINGS['known_errors']:
                        if error.lower() in issue['reason'].lower():
                            link = config.SETTINGS['wiki'] + '/'
                            link += '+'.join(error.split())
                            message = f'[{error}|{link}]'
                            issue['comment'] = make_comment(issue, message)
                            break

                issues.append(issue)

        comment = ''
        issue_can_be_closed = True
        for issue in issues:
            if not issue['comment']:
                issue_can_be_closed = False
                reason = make_comment(issue, issue['reason'])
                comment += f'{reason}\n'
            else:
                comment += f'{issue["comment"]}\n'

        if not comment:
            comment = 'No problem was found'

        jql = (f'project = SOX AND '
               f'summary ~ "JobSummary_\\\\[{service_name}\\\\]" AND '
               f'created >= startOfDay()')
        issue = jira.search_issues(jql, validate_query=True)[0]
        issue_status = issue.fields.status.name.lower()

        if issue_status == 'open':
            jira.add_comment(issue.key, comment)
            comment = comment.replace('\n', '|')

            if issue_can_be_closed:
                # list of transitions /rest/api/2/issue/${issueIdOrKey}/transitions
                jira.transition_issue(issue=issue.key, transition='Close')
                logger.info(f'{service_name} ({issue.key}) has been closed')
        else:
            logger.info(f'{service_name} ({issue.key}) has already been closed')


def make_comment(issue, message):
    return f'{issue["client"]} ({issue["job_id"]}): {message}'


if __name__ == '__main__':
    main()
