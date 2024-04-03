
import os
import re
import logging
import subprocess
from tabulate import tabulate

from telegram import Update, ReplyKeyboardMarkup, ReplyKeyboardRemove

from telegram.ext import (
    Application,
    CommandHandler,
    ContextTypes,
    ConversationHandler,
)

from telegram import Bot

from functools import wraps

logging.basicConfig(
    format="%(asctime)s \- %(name)s \- %(levelname)s \- %(message)s", level=logging.INFO
)

logging.getLogger("httpx").setLevel(logging.WARNING)
logger = logging.getLogger(__name__)

# define states
TRACKING, CHOOSING, CHOOSE_JOB_TO_TRACK = range(3)

LIST_OF_USERS = ["st3p99"]
TOKEN = os.environ.get('SLURM_BOT_TOKEN') 

# Decorator to restrict access to the bot
def restricted(func):
    @wraps(func)
    def wrapped(update, context, *args, **kwargs):
        user_id = update.message.from_user.username
        if user_id not in LIST_OF_USERS:
            print("Unauthorized access denied for {}.".format(user_id))
            return
        return func(update, context, *args, **kwargs)
    return wrapped

@restricted
async def list_slurm_jobs(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    logger.info("Listing SLURM jobs")
    jobs_info = subprocess.run(
        ["sacct", "--format", "JobID,JobName,User,State,Elapsed", "--parsable2"],
        capture_output=True,
        text=True
    )

    data = jobs_info.stdout

    rows = [[cell.strip() for cell in row.split("|")] for row in data.strip().split("\n")]

    #take the first 25 rows to avoid too large messages (bad request error)
    rows = rows[:25]

    markdown_table = tabulate(rows, tablefmt="rounded_grid", headers="firstrow")

    formatted_output = "<pre>{}</pre>".format(markdown_table)
    try:
        await update.message.reply_text(
            formatted_output,
            parse_mode='HTML')
    except Exception as e:
        logger.error(f"Error sending message: {e}")
        await update.message.reply_text(f"Error sending message: {e}")

    return CHOOSING

@restricted
async def queue(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    logger.info("Listing queue")
    jobs_info = subprocess.run(
        ["squeue", "--format", "%i %j %u %T %S"], capture_output=True, text=True
    )

    lines = jobs_info.stdout.splitlines()

    table = tabulate([line.split() for line in lines], tablefmt="rounded_grid", headers="firstrow")

    formatted_output = "<pre>{}</pre>".format(table)
    try:
        await update.message.reply_text(
            formatted_output,
            parse_mode='HTML')
    except Exception as e:
        logger.error(f"Error sending message: {e}")
        await update.message.reply_text(f"Error sending message: {e}")
    return CHOOSING

@restricted
async def start_tracking(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    logger.info("Choose job to track")

    jobs_info = subprocess.run(
        ["squeue", "--format", "%i %j %u %T"], capture_output=True, text=True
    )

    lines = jobs_info.stdout.splitlines()

    jobs_queue = {int(i+1): line.split() for i, line in enumerate(lines[1:])}

    if not jobs_queue:
        await update.message.reply_text("No jobs to track.")
        return CHOOSING

    lines[0] = "ID " + lines[0]
    for i, line in enumerate(lines[1:], start=1):
        lines[i] = f"{i} {line}"

    table = tabulate([line.split() for line in lines], tablefmt="rounded_grid", headers="firstrow")

    formatted_output = "<pre>{}</pre>".format(table)

    context.bot_data["jobs"] = jobs_queue

    reply_keyboard = [[f"/track_job {i}" for i in range(1, len(jobs_queue) + 1)], ["/back"]]
    await update.message.reply_text(
        f"Choose a job to track:\n\n{formatted_output}",
        parse_mode='HTML',
        reply_markup=ReplyKeyboardMarkup(
            reply_keyboard, one_time_keyboard=True, input_field_placeholder="Type command here"
        ),
    )
    
    return CHOOSE_JOB_TO_TRACK


async def track_slurm_job(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    logger.info("Tracking SLURM job")
    command = update.message.text.strip()
    job_id = command.split(" ")[1] if len(command.split(" ")) > 1 else None

    job = context.bot_data["jobs"].get(int(job_id))
    if not job:
        await update.message.reply_text("Job not found.")
        return CHOOSING
    
    logger.info(f"Tracking job {job_id} - {job}")

    await update.message.reply_text(f"Tracking job {job_id} - {job}", 
                                    reply_markup=ReplyKeyboardMarkup([["/stop_tracking", "/send_stdout", "/send_stderr"]], 
                                    one_time_keyboard=True, input_field_placeholder="Type command here"))
    
    context.bot_data["tracking_job"] = job[0]
    context.bot_data["tracking_job_state"] = job[3]

    context.job_queue.run_repeating(check_job_state, interval=120, chat_id=update.message.chat_id, name="tracking")
    return TRACKING

async def check_job_state(context):
    job_id = context.bot_data["tracking_job"]
    job_state = context.bot_data["tracking_job_state"]
    scontrol_output = subprocess.run(["scontrol", "show", "job", job_id], capture_output=True, text=True).stdout
    state_pattern = r'JobState=(\S*)'
    state_match = re.search(state_pattern, scontrol_output)
    if state_match:
        new_state = state_match.group(1)
        if new_state != job_state:
            context.bot_data["tracking_job_state"] = new_state
            message = f"Job {job_id} changed state from {job_state} to {new_state}"
            await send_message_to_chat_id(message, context.job.chat_id)
            if new_state == "COMPLETED" or new_state == "CANCELLED" or new_state == "FAILED":
                await send_message_to_chat_id("Please: /stop_tracking", context.job.chat_id)
                #TODO: find a way to execute /stop_tracking command from here
    else:
        logger.error("State not found")
        await send_message_to_chat_id("State not found", context.job.chat_id)
        await send_message_to_chat_id("Please: /stop_tracking", context.job.chat_id)

    return

@restricted
async def stop_tracking(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    logger.info("Stop tracking SLURM job")

    context.job_queue.get_jobs_by_name("tracking")[0].schedule_removal()
    context.bot_data["jobs"].clear()
    context.bot_data["tracking_job"] = None
    
    
    reply_keyboard = [["/list_jobs", "/queue", "/start_tracking", "/send_stdout <job_id>", "/send_stderr <job_id>"]]
    await update.message.reply_text(
        "Tracking stopped. ",
        reply_markup=ReplyKeyboardMarkup(
            reply_keyboard, one_time_keyboard=True, input_field_placeholder="Type command here"
        ),
    )

    return CHOOSING

@restricted
async def send_stdout(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    command = update.message.text.strip()   
    if context.bot_data.get("tracking_job"):
        job_id = context.bot_data.get("tracking_job")
    else:
        job_id = command.split(" ")[1] if len(command.split(" ")) > 1 else None
    if not job_id:
        await update.message.reply_text("Please provide a job ID. Usage: /send_stdout <job_id>")
        return CHOOSING
    
    logger.info(f"Sending stdout file for job {job_id}")

    scontrol_output = subprocess.run(["scontrol", "show", "job", job_id], capture_output=True, text=True).stdout

    stdout_pattern = r'StdOut=(\S*)'
    stdout_match = re.search(stdout_pattern, scontrol_output)
    if stdout_match:
        stdout_path = stdout_match.group(1)
        logger.info(f"StdOut path: {stdout_path}")
        try:
            await context.bot.send_document(chat_id=update.effective_chat.id, document=open(stdout_path, 'rb'), filename=f"stdout_{job_id}.txt")
        except FileNotFoundError:
            logger.error(f"StdOut file not found: {stdout_path}")
            await update.message.reply_text(f"StdOut file not found: {stdout_path}")
        except PermissionError:
            logger.error(f"Permission denied to read StdOut file: {stdout_path}")
            await update.message.reply_text(f"Permission denied to read StdOut file: {stdout_path}")
        except Exception as e:
            logger.error(f"Error sending StdOut file: {e}")
            await update.message.reply_text(f"Error sending StdOut file: {e}")
    else:
        logger.error("StdOut path not found")
        await update.message.reply_text("StdOut path not found")

    return CHOOSING

@restricted
async def send_stderr(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    command = update.message.text.strip()
    if context.bot_data.get("tracking_job"):
        job_id = context.bot_data.get("tracking_job")
    else:
        job_id = command.split(" ")[1] if len(command.split(" ")) > 1 else None
    if not job_id:
        await update.message.reply_text("Please provide a job ID. Usage: /send_stderr <job_id>")
        return CHOOSING
    
    logger.info(f"Sending stderr file for job {job_id}")

    scontrol_output = subprocess.run(["scontrol", "show", "job", job_id], capture_output=True, text=True).stdout

    stderr_pattern = r'StdErr=(\S*)'
    stderr_match = re.search(stderr_pattern, scontrol_output)
    if stderr_match:
        stderr_path = stderr_match.group(1)
        logger.info(f"StdErr path: {stderr_path}")
        try:
            await context.bot.send_document(chat_id=update.effective_chat.id, document=open(stderr_path, 'rb'), filename=f"stderr_{job_id}.txt")
        except FileNotFoundError:
            logger.error(f"StdErr file not found: {stderr_path}")
            await update.message.reply_text(f"StdErr file not found: {stderr_path}")
        except PermissionError:
            logger.error(f"Permission denied to read StdErr file: {stderr_path}")
            await update.message.reply_text(f"Permission denied to read StdErr file: {stderr_path}")
        except Exception as e:
            logger.error(f"Error sending StdErr file: {e}")
            await update.message.reply_text(f"Error sending StdErr file: {e}")
    else:
        logger.error("StdErr path not found")
        await update.message.reply_text("StdErr path not found")

    return CHOOSING

@restricted
async def start(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """Starts the conversation and asks the user about their gender."""
    reply_keyboard = [["/list_jobs", "/queue", "/start_tracking", "/send_stdout <job_id>", "/send_stderr <job_id>"]]

    await update.message.reply_text(
        "Hi! I'm your SLURM job tracker bot. "
        "You can use the following commands: /list_jobs, /queue, /start_tracking, /send_stdout <job_id> and /send_stderr <job_id>\n\n"
        "Type one of the commands:",
        reply_markup=ReplyKeyboardMarkup(
            reply_keyboard, one_time_keyboard=True, input_field_placeholder="Type command here"
        ),
    )

    return CHOOSING

@restricted
async def back(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    reply_keyboard = [["/list_jobs", "/queue", "/start_tracking", "/send_stdout <job_id>", "/send_stderr <job_id>"]]

    await update.message.reply_text(
        "Choose a command from the list: /list_jobs, /queue, /start_tracking, /send_stdout <job_id> and /send_stderr <job_id>",
        reply_markup=ReplyKeyboardMarkup(
            reply_keyboard, one_time_keyboard=True, input_field_placeholder="Type command here"
        ),
    )

    return CHOOSING

@restricted
async def cancel(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
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
    
    conv_handler = ConversationHandler(
        entry_points=[CommandHandler("start", start)],
        states={
            TRACKING: [CommandHandler("stop_tracking", stop_tracking),CommandHandler("send_stdout", send_stdout),
                CommandHandler("send_stderr", send_stderr),CommandHandler("back", back)],
            
            CHOOSING: [
                CommandHandler("list_jobs", list_slurm_jobs),
                CommandHandler("queue", queue),
                CommandHandler("start_tracking", start_tracking),
                CommandHandler("send_stdout", send_stdout),
                CommandHandler("send_stderr", send_stderr),
            ],
            CHOOSE_JOB_TO_TRACK: [CommandHandler("track_job", track_slurm_job), CommandHandler("back", back)],
        },
        fallbacks=[CommandHandler("cancel", cancel)],
    )

    application = Application.builder().token(TOKEN).build()
 
    application.add_handler(conv_handler)
    
    # Run the bot until the user presses Ctrl\-C
    application.run_polling(allowed_updates=Update.ALL_TYPES)

if __name__ == "__main__":
    main()
