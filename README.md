# Commvault scripts

The collection of scripts to automate daily Commvault tasks.



## Installation

Use the package manager [pip](https://pip.pypa.io/en/stable/) or [pipenv](https://github.com/pypa/pipenv):
```sh
# pip
pip install -r requirements.txt

# pipenv
pipenv install --ignore-pipfile
```

Environment variables:

| Variable             | Required | Example       |
|----------------------|----------| --------------|
| `COMMVAULT_USERNAME` | yes      | contoso\admin |
| `COMMVAULT_PASSWORD` | yes      | TopSecret     |
| `JIRA_USERNAME`      | yes      | jirabot       |
| `JIRA_PASSWORD`      | yes      | TopSecret     |
| `SMTP_USERNAME`      | yes      | smtpbot       |
| `SMTP_PASSWORD`      | yes      | TopSecret     |

Files `settings.yml` and `services.ini` must have located into project's root. You can copy prepared templates from `./example` to root directory and modify them if needed.

All logs files write into `./logs` directory. If the directory doesn'n exist, it'll be created automaticaly after running any script.



## Usage

### Active tasks

This script looks for unresolved issues in the Jira project and notifies via email if there are such issues.

You can configure the email sender and/or recipients in the `settings.yml` (section `smtp`).

```sh
python active-tasks.py
```

### Service details

This scripts gets the list of services from `services.ini` and obtains their clients configuration from Commvault. After that, it renders service's parameters using `templates/service.yml.j2` and save report into `./reports` directory.

**IMPORTANT:** services from `services.ini` should have the same name as Client Group in the Commvault.

```sh
python active-tasks.py
```

### SOX opened tasks

This script looks for opened issues in the SOX project for 7 days and notifies all responsibles via email if there are such issues.

It looks for services by name are listed in the `settings.yml` (sections `sox_services`, `admin_services`).

```sh
python sox-opened-tasks.py
```

### SOX parser

This script retrieves the list of SOX-services from `settings.yml` (section **sox_services**), obtains all jobs for last 24 hours (section **commvault**) for each service. If the service doesn't have jobs with critical/unknown errors (section **known_errors**), the script will leave a comment that all is fine in the issue and close it. Otherwise, it will only leave a comment with detail information about each critical/unknown error. If the error is documented in the Wiki (section **wiki**), the comment will have a link to the article in the Wiki.

```sh
python sox-parser.py
```

### Suspend jobs

This script resume/suspend Data Verification jobs based on the first CLI argument took.

```sh
# resume suspended jobs if there are
python suspend-jobs.py resume

# suspend running jobs if there are
python suspend-jobs.py suspend
```
