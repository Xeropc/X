import discord
from discord.ext import commands
import os
import requests
import threading
import time
from flask import Flask

# === Keep Alive Webserver + Self-Pinger ===
app = Flask('')

@app.route('/')
def home():
    return "Bot is running!"

def run_server():
    app.run(host='0.0.0.0', port=8080)

def keep_alive():
    # start flask webserver
    t = threading.Thread(target=run_server)
    t.daemon = True
    t.start()

    # start self-pinger in background
    def auto_ping():
        url = "https://b201675c-f07f-4c3f-845c-ad88999fb713-00-2e2f8ewjtjgu5.riker.replit.dev/"  # your actual Repl URL
        while True:
            try:
                requests.get(url)
                print("🔄 Pinged self to stay awake")
            except Exception as e:
                print("Ping failed:", e)
            time.sleep(300)  # every 5 minutes

    pinger = threading.Thread(target=auto_ping)
    pinger.daemon = True
    pinger.start()

# === Discord Bot ===
intents = discord.Intents.default()
intents.message_content = True  # allow reading messages for commands
bot = commands.Bot(command_prefix="!", intents=intents)

@bot.event
async def on_ready():
    print(f"✅ Logged in as {bot.user}")

    activity = discord.Activity(
        type=discord.ActivityType.watching,   # non-clickable
        name="Servers"
    )
    await bot.change_presence(status=discord.Status.online, activity=activity)

# === Ping Command ===
@bot.command()
async def ping(ctx):
    await ctx.message.delete()
    await ctx.send("I'm still awake and watching servers.", delete_after=3)  # custom message

@bot.command()
async def x(ctx):
    await ctx.message.delete()
    message = (
        "🛡️ **XERO Protection System**\n"
        "DDoS Protection Activated ✅\n"
        "All servers are safe and monitored."
    )
    await ctx.send(message, delete_after=3)

# === Start Everything ===
keep_alive()
bot.run(os.getenv("TOKEN"))
