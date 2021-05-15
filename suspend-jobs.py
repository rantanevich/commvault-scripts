#!/usr/bin/env python3
'''
It suspends/resumes Data Verification jobs.

It make a decision with the first CLI argument (resume/suspend).
'''
import sys

from cvpysdk.commcell import Commcell
from cvpysdk.job import JobController

import config
from config import logger


logger.add(sink=config.LOG_DIR / 'suspend-jobs.log',
           rotation=config.SETTINGS['logging']['rotation'],
           format=config.SETTINGS['logging']['format'],
           level='INFO')


@logger.catch
def main():
    commvault = Commcell(**config.COMMVAULT)
    job_controller = JobController(commvault)

    # DATA_VERIFICATION
    jobs = job_controller.active_jobs(job_type_list=[31])

    for job_id in jobs:
        job = job_controller.get(job_id)

        if job.status == 'Suspended' and sys.argv[1] == 'resume':
            job.resume(wait_for_job_to_resume=True)
            logger.info(f'job ({job_id}) has been resumed')

        elif job.status == 'Running' and sys.argv[1] == 'suspend':
            job.pause(wait_for_job_to_pause=True)
            logger.info(f'job ({job_id}) has been suspended')

    commvault.logout()


if __name__ == '__main__':
    main()
