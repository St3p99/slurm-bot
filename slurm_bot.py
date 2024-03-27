import logging
import subprocess
from telegram import Update, ReplyKeyboardMarkup, ReplyKeyboardRemove

from telegram.ext import (
    Application,
    CommandHandler,
    ContextTypes,
    ConversationHandler,
    MessageHandler,
    filters,
)

from telegram import Bot

from functools import wraps
import os


logging.basicConfig(
    format="%(asctime)s \- %(name)s \- %(levelname)s \- %(message)s", level=logging.INFO
)
# set higher logging level for httpx to avoid all GET and POST requests being logged
logging.getLogger("httpx").setLevel(logging.WARNING)
logger = logging.getLogger(__name__)


#STATES
TRACKING, CHOOSING = range(2)

LIST_OF_USERS = ["@username1", "@username2"] # list of authorized users to access the bot
TOKEN = os.environ.get('SLURM_BOT_TOKEN') 

class SlurmBot:
    def __init__(self):
        self.application = Application.builder().token(TOKEN).build()

        # Add conversation handler
        conv_handler = ConversationHandler(
            entry_points=[CommandHandler("start", SlurmBot._start)],
            states={
                TRACKING: [CommandHandler("stop_tracking", SlurmBot._stop_tracking)],
                #choosing expects a command from the user (list_jobs, track_job, stop_tracking, send_stdout, send_stderr)
                CHOOSING: [
                    CommandHandler("list_jobs", SlurmBot._list_slurm_jobs),
                    CommandHandler("track_job", SlurmBot._track_slurm_job),
                    CommandHandler("send_stdout", SlurmBot._send_stdout),
                    CommandHandler("send_stderr", SlurmBot._send_stderr),
                ]
            },
            fallbacks=[CommandHandler("cancel", SlurmBot._cancel)],
        )

        # Add the conversation handler to the application
        self.application.add_handler(conv_handler)
        # Run the bot until the user presses Ctrl\-C
        self.application.run_polling(allowed_updates=Update.ALL_TYPES)


    def _restricted(func):
        @wraps(func)
        def wrapped(update, context, *args, **kwargs):
            # user_id = update.effective_user.id
            user_id = update.message.from_user.username
            if user_id not in LIST_OF_USERS:
                print("Unauthorized access denied for {}.".format(user_id))
                return
            return func(update, context, *args, **kwargs)
        return wrapped

    @_restricted
    async def _list_slurm_jobs(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
        logger.info("Listing SLURM jobs")
        jobs_info = subprocess.run(
            ["squeue", "--format", "%i %P %j %u %t %M %D %R"], capture_output=True, text=True
        )

        lines = jobs_info.stdout.splitlines()
        
    #    telegram.error.BadRequest: Can't parse entities: character '\|' is reserved and must be escaped with the preceding '\'
        formatted_output = ""
        # Adding column headers to the formatted output
        formatted_output += "| {:<6} | {:<15} | {:<15} | {:<10} | {:<2} | {:<5} | {:2} |\n".format(*lines[0].split())
        formatted_output += "|" + "-"*8 + "|" + "-"*17 + "|" + "-"*17 + "|" + "-"*12 + "|" + "-"*4 + "|" + "-"*7 + "|" + "-"*4 + "|\n"

        # Adding formatted data to the output
        for line in lines[1:]:
            job_id, partition, name, user, st, time, nodes, nodelist_reason = line.split(maxsplit=7)
            #escape special characters in job_id, partition, name, user, st, time, nodes, nodelist_reason
            # partition = partition.replace("-", "\-")
            # name = name.replace("-", "\-")

            formatted_output += "| {:<6} | {:<15} | {:<15} | {:<10} | {:<2} | {:<5} | {:2} |\n".format(job_id, partition, name, user, st, time, nodes, nodelist_reason)
        #wrap message with <pre> and </pre> tags to preserve formatting
        formatted_output = "<pre style='overflow-x: auto;'>{}</pre>".format(formatted_output)
        await update.message.reply_text(
            formatted_output,
            parse_mode='HTML')

        return CHOOSING

    @_restricted
    async def _track_slurm_job(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
        command = update.message.text.strip()
        job_id = command.split(" ")[1] if len(command.split(" ")) > 1 else None
        logger.info(f"Tracking SLURM job {job_id}")
        if job_id is None:
            await update.message.reply_text("Please provide a job id to track.")
            return CHOOSING
        # Your tracking logic here
        return TRACKING

    @_restricted
    async def _stop_tracking(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
        logger.info("Stop tracking SLURM job")
        # Your reset logic here
        return CHOOSING

    @_restricted
    async def _send_stdout(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
        command = update.message.text.strip()
        job_id = command.split(" ")[1] if len(command.split(" ")) > 1 else None
        logger.info(f"Sending stdout file for job {job_id}")
        # Your logic to send stdout file here
        stdout = subprocess.run(["scontrol", "show", "job", job_id], capture_output=True, text=True)
        await update.message.reply_text(stdout.stdout)
        return CHOOSING

    @_restricted
    async def _send_stderr(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
        command = update.message.text.strip()
        job_id = command.split(" ")[1] if len(command.split(" ")) > 1 else None
        logger.info(f"Sending stderr file for job {job_id}")
        # Your logic to send stderr file here
        return CHOOSING

    @_restricted
    async def _start(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
        """Starts the conversation and asks the user about their gender."""
        reply_keyboard = [["/list_jobs", "/track_job", "/stop_tracking", "/send_stdout", "/send_stderr"]]

        await update.message.reply_text(
            "Hi! I'm your SLURM job tracker bot. "
            "You can use commands like /list_jobs, /track_job, /stop_tracking, /send_stdout, and /send_stderr.\n\n"
            "Type one of the commands:",
            reply_markup=ReplyKeyboardMarkup(
                reply_keyboard, one_time_keyboard=True, input_field_placeholder="Type command here"
            ),
        )

        return CHOOSING

    @_restricted
    async def _cancel(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
        """Cancels and ends the conversation."""
        await update.message.reply_text(
            "Bye! I hope we can talk again some day.", reply_markup=ReplyKeyboardRemove()
        )

        return ConversationHandler.END


    async def send_message_to_chat_id(message, chat_id):
        bot = Bot(token=TOKEN)
        await bot.send_message(chat_id=chat_id, text=message)

def main() -> None:
    """Run the bot."""
    SlurmBot()


if __name__ == "__main__":
    main()
