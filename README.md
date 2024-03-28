# SLURM Bot

SLURM Bot is a Telegram bot that allows you to track and manage SLURM jobs. It provides useful commands to list jobs, view the job queue, start tracking a job, and send the standard output and standard error files of a job.

## Getting Started

To use SLURM Bot, you need to have a Telegram account and join the bot's chat. Once you have joined the chat, you can start using the available commands.

## Available Commands

- `/list_jobs`: Lists the SLURM jobs and their details (sacct SLURM command).
- `/queue`: Lists the SLURM job queue (squeue SLURM command)
- `/start_tracking`: Starts tracking a specific SLURM job.
- `/send_stdout <job_id>`: Sends the standard output file of a specific SLURM job (if available).
- `/send_stderr <job_id>`: Sends the standard error file of a specific SLURM job (if available).

## Usage

1. Start the bot by sending the `/start` command.
2. Choose a command from the list of available commands.
3. Follow the instructions provided by the bot to perform the desired action.

## Authorization

The `SLURM_BOT_TOKEN` is a unique identifier that allows the bot to connect to the Telegram Bot API. It is required for the bot to function properly. To obtain a `SLURM_BOT_TOKEN`, you need to create a new bot on the Telegram platform and obtain the token from the BotFather.

Once you have obtained the `SLURM_BOT_TOKEN`, you can set it as an environment variable or directly replace the placeholder value in the code with your token.


Access to the bot is restricted to authorized users. Only users listed in the `LIST_OF_USERS` variable in the code are allowed to access the bot. Unauthorized access attempts will be denied.

## Dependencies

SLURM Bot requires the following dependencies:

- `tabulate`: A Python library for creating formatted tables.
- [`python-telegram-bot`](https://docs.python-telegram-bot.org/en/stable/index.html): A Python wrapper for the Telegram Bot API.

You can install the dependencies by running the following command:

```bash
pip install tabulate
pip install "python-telegram-bot[job-queue]"
```

