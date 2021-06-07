#!/usr/bin/env python3
'''
Takes clients from chosen Client Group and create a high-level view of the clients' settings.
'''
import re
import socket
from datetime import datetime
from base64 import b64encode
from configparser import ConfigParser
from collections import defaultdict
from json.decoder import JSONDecodeError

from loguru import logger
from jinja2 import Template
from requests import Session
from requests.adapters import HTTPAdapter
from urllib.parse import urljoin
from urllib3.util.retry import Retry

import config


CONFIG_FILE = config.BASE_DIR / 'services.ini'

TEMPLATE_FILE = config.BASE_DIR / 'templates' / 'service.yml.j2'
TEMPLATE = Template(TEMPLATE_FILE.read_text(encoding='utf8'))

REPORTS_DIR = config.BASE_DIR / 'reports'
REPORTS_DIR.mkdir(exist_ok=True)

REQUEST_TIMEOUT = 30
RETRY_STRATEGY = Retry(
    total=3,
    backoff_factor=2,
    status_forcelist=[429, 500, 502, 503, 504]
)

BACKUP_LEVEL = {
    4: 'SynFull',
    3: 'Differential',
    2: 'Incremental',
    1: 'Full',
}


class BaseUrlSession(Session):
    '''A Session with a URL that all requests will use as a base'''

    def __init__(self, base_url):
        self.base_url = base_url
        Session.__init__(self)

    def request(self, method, url, *args, **kwargs):
        '''Send the request after generating the complete URL'''
        url = self.create_url(url)
        return Session.request(self, method, url, *args, **kwargs)

    def create_url(self, url):
        '''Create the URL based off the partial path'''
        return urljoin(self.base_url, url)


class TimeoutHTTPAdapter(HTTPAdapter):
    '''HTTPAdapter with a default timeout'''

    def __init__(self, *args, **kwargs):
        self.timeout = kwargs.pop('timeout', REQUEST_TIMEOUT)
        HTTPAdapter.__init__(self, *args, **kwargs)

    def send(self, request, **kwargs):
        kwargs['timeout'] = kwargs.get('timeout', self.timeout)
        return HTTPAdapter.send(self, request, **kwargs)


@logger.catch
def main():
    session = commvault_login()
    logger.info('Commvault session is created')

    resp_json = query_api(session, 'GET', 'ClientGroup')
    client_groups = {item['name']: item['Id'] for item in resp_json['groups']}
    logger.info(f'client groups: {len(client_groups)}')

    for service_name in get_services_from_file():
        logger.info(f'service: {service_name}')
        client_group_id = client_groups[service_name]

        resp_json = query_api(session, 'GET', f'ClientGroup/{client_group_id}')
        clients = [(item['clientId'], item['clientName'])
                   for item in resp_json['clientGroupDetail']['associatedClients']]
        logger.info(f'clients: {clients}')

        servers = []
        for client_id, client_name in clients:
            logger.info(f'client: {client_name}')
            resp_json = query_api(session, 'GET', f'Subclient/?clientId={client_id}')
            subclients = []
            for node in resp_json.get('subClientProperties', []):
                subclients.append(node['subClientEntity'])

            resp_json = query_api(session, 'GET', f'Client/{client_id}')
            client_props = resp_json['clientProperties'][0]
            operating_system = client_props['client']['osInfo']['OsDisplayInfo']['OSName']

            virtual_machine = client_props.get('vmStatusInfo')
            if virtual_machine and virtual_machine.get('subclientName'):
                subclients.append(virtual_machine['vsaSubClientEntity'])
            logger.info(f'subclients: {len(subclients)}')

            agents = defaultdict(list)
            for node in subclients:
                subclient_id = node['subclientId']
                subclient_name = node['subclientName']
                logger.info(f'subclient: {subclient_name}')

                agent = node['appName']
                if agent in ('Oracle', 'SQL Server', 'MySQL'):
                    backupset = None
                    instance = node['instanceName']
                else:
                    backupset = node['backupsetName']
                    instance = None

                resp_json = query_api(session, 'GET', f'Subclient/{subclient_id}')
                subclient_props = resp_json['subClientProperties'][0]
                subclient_status = subclient_props['commonProperties']['enableBackup']

                last_job = {}
                job_info = subclient_props['commonProperties'].get('lastBackupJobInfo')
                if job_info and job_info.get('jobID'):
                    job_id = job_info['jobID']
                    resp_json = query_api(session, 'GET', f'Job/{job_id}')

                    try:
                        job_summary = resp_json['jobs'][0]['jobSummary']
                    except KeyError:
                        job_summary = {'status': 'Not Found',
                                       'jobStartTime': None,
                                       'jobEndTime': None}

                    last_job['id'] = job_id
                    last_job['status'] = job_summary['status']
                    last_job['started'] = timestamp_to_datetime(job_summary['jobStartTime'])
                    last_job['finished'] = timestamp_to_datetime(job_summary['jobEndTime'])

                content = defaultdict(list)
                if node['appName'] == 'File System':
                    for item in subclient_props['content']:
                        include = item.get('path') or item.get('includePath')
                        if include:
                            content['include'].append(include)
                        else:
                            content['exclude'].append(item['excludePath'])

                resp_json = None
                backup_storage_policy = subclient_props['commonProperties']['storageDevice']['dataBackupStoragePolicy']
                if backup_storage_policy.get('storagePolicyId'):
                    policy_id = backup_storage_policy['storagePolicyId']
                    resp_json = query_api(session, 'GET', f'StoragePolicy/{policy_id}')

                storage_policy = {}
                if resp_json and resp_json.get('copy'):
                    retention = resp_json['copy'][0]['retentionRules']
                    retain_days = retention['retainBackupDataForDays']
                    retain_cycles = retention['retainBackupDataForCycles']
                    storage_policy['name'] = backup_storage_policy.get('storagePolicyName')
                    storage_policy['retention'] = f'{retain_days} days, {retain_cycles} cycles'

                resp_json = query_api(session, 'GET', f'Schedules/?subclientId={subclient_id}')

                schedules = []
                if resp_json:
                    task = resp_json['taskDetail'][0]
                    for sub_task in task['subTasks']:
                        level = BACKUP_LEVEL[sub_task['options']['backupOpts']['backupLevel']]
                        description = sub_task['pattern']['description'].strip()
                        description = re.sub(' starting .+?and', 'and', description)
                        schedules.append({'type': level, 'pattern': description})

                agents[agent].append({
                    'name': subclient_name,
                    'backupset': backupset,
                    'instance': instance,
                    'status': subclient_status,
                    'content': content,
                    'storage_policy': storage_policy,
                    'schedules': schedules,
                    'last_job': last_job,
                })

            # before: agents = {'agent_1': [subclients], ...}
            # after:  agents = {'agent_1': {'backupsets': [subclients]}, ...}
            for agent_name in agents:
                if agents[agent_name][0]['backupset']:
                    agents[agent_name] = {'backupsets': agents[agent_name]}
                else:
                    agents[agent_name] = {'instances': agents[agent_name]}

            # before: agents = {'agent_1': {'backupsets': [subclients]}, ...}
            # after:  agents = {'agent_1': {'backupsets': {'backupset_1': [subclients], ...}}, ...}
            for agent_name in agents:
                if agents[agent_name].get('backupsets'):
                    tmp = defaultdict(list)
                    for subclient in agents[agent_name]['backupsets']:
                        tmp[subclient['backupset']].append(subclient)
                    agents[agent_name]['backupsets'] = tmp
                else:
                    tmp = defaultdict(list)
                    for subclient in agents[agent_name]['instances']:
                        tmp[subclient['instance']].append(subclient)
                    agents[agent_name]['instances'] = tmp

            servers.append({
                'hostname': client_name,
                'os': operating_system,
                'agents': agents,
            })

        current_time = datetime.now()

        report_file = REPORTS_DIR / f'{service_name}_{current_time.strftime("%Y%m%d%H%M")}.yml'
        report_file.write_text(TEMPLATE.render(current_time=current_time,
                                               service_name=service_name,
                                               servers=servers),
                               encoding='utf8')
        logger.info(f'{report_file} is created')
    commvault_logout(session)
    logger.info('Commvault session is closed')


def commvault_login():
    '''Make login request'''
    hostname = config.COMMVAULT['webconsole_hostname']
    adapter = TimeoutHTTPAdapter(max_retries=RETRY_STRATEGY)

    session = BaseUrlSession(f'http://{hostname}/webconsole/api/')
    session.mount('http://', adapter)
    session.mount('https://', adapter)
    session.headers.update({'Accept': 'application/json',
                            'Content-Type': 'application/json'})

    resp_json = query_api(session, 'POST', 'Login', payload={
        'mode': 4,
        'username': config.COMMVAULT['commcell_username'],
        'password': b64encode(config.COMMVAULT['commcell_password'].encode()).decode(),
        'deviceId': socket.getfqdn(),
        'clientType': 30,
    })
    session.headers['Authtoken'] = resp_json['token']
    return session


def commvault_logout(session):
    '''Make logout request'''
    query_api(session, 'POST', 'Logout')
    session.close()


def query_api(session, method, path, payload=None):
    '''Make the API request to the Commcell'''
    if method == 'POST' and not payload:
        session.headers['Content-Type'] = 'application/xml'
    else:
        session.headers['Content-Type'] = 'application/json'

    try:
        response = session.request(method, path, json=payload)
        response.raise_for_status()
        return response.json()
    except JSONDecodeError:
        return response


def timestamp_to_datetime(timestamp):
    '''Convert timestamp to datetime instance'''
    if timestamp:
        return datetime.fromtimestamp(timestamp).strftime('%T %d.%m.%Y')


def get_services_from_file():
    '''Extract a list of services from configuration file'''
    config = ConfigParser(allow_no_value=True)
    config.optionxform = str    # case-sensitive
    config.read(CONFIG_FILE, encoding='utf8')
    return [service for service in config['services']]


if __name__ == '__main__':
    main()
