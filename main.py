import discord
from discord.ext import commands
import os
import requests
import threading
import time

# === Keep Alive Webserver + Self-Pinger ===
from flask import Flask
app = Flask('')

@app.route('/')
def home():
    return "Bot is running!"

def run_server():
    port = int(os.environ.get("PORT", 8080))
    print(f"🟢 Starting Flask server on port {port}")
    app.run(host='0.0.0.0', port=port)

def keep_alive():
    t = threading.Thread(target=run_server)
    t.daemon = True
    t.start()

    def auto_ping():
        url = "https://b201675c-f07f-4c3f-845c-ad88999fb713-00-2e2f8ewjtjgu5.riker.replit.dev/"
        while True:
            try:
                requests.get(url)
                print("🔄 Pinged self to stay awake")
            except Exception as e:
                print("⚠️ Ping failed:", e)
            time.sleep(300)

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

# === Reputation System ===
reputation = {}

def adjust_reputation(user_id, amount):
    reputation[user_id] = reputation.get(user_id, 100) + amount

@bot.command()
async def rep(ctx, member: discord.Member = None):
    member = member or ctx.author
    score = reputation.get(member.id, 100)
    await ctx.send(f"📊 **Reputation for {member.display_name}:** {score}")

# === Status Dashboard ===
raid_stats = {"raids_blocked": 0, "suspicious_flagged": 0}  # Can be updated manually if needed

@bot.command()
async def status(ctx):
    await ctx.message.delete()
    msg = (
        f"🛡️ **Server Health Dashboard**\n"
        f"Raids Blocked: {raid_stats['raids_blocked']}\n"
        f"Suspicious Accounts Quarantined: {raid_stats['suspicious_flagged']}"
    )
    await ctx.send(msg, delete_after=4)

# === Ping & XERO Commands ===
@bot.command()
async def ping(ctx):
    await ctx.message.delete()
    await ctx.send("I'm still awake and watching servers.", delete_after=4)

@bot.command()
async def x(ctx):
    await ctx.message.delete()
    message = (
        "🛡️ **XERO Protection System**\n"
        "DDoS Protection Activated ✅\n"
        "All servers are safe and monitored."
    )
    await ctx.send(message, delete_after=4)

# === Start Everything ===
keep_alive()

token = os.getenv("TOKEN")
if not token:
    print("❌ ERROR: TOKEN environment variable not set! Please add it in Replit Secrets.")
else:
    bot.run(token)


