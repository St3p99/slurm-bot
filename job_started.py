import asyncio

import argparse
import os
from slurm_bot import SlurmBot

CHAT_ID = os.environ.get('SLURM_BOT_CHAT_ID')

async def create_message(job_id, job_name):
    if job_name is None:
        message_text = f"Job {job_id} has started."
    else:
        message_text = f"Job {job_id} ({job_name}) has started."
    await SlurmBot.send_message_to_chat_id(message_text, CHAT_ID)

if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--job-id", help="Job ID")
    parser.add_argument("--job-name", help="Job Name", default=None)
    args = parser.parse_args()

    job_id = args.job_id
    job_name = args.job_name

    asyncio.run(create_message(job_id, job_name))

