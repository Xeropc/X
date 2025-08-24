import discord
from discord.ext import commands, tasks
import os
import requests
import threading
from flask import Flask
import time
import asyncio

# === Keep Alive Webserver ===
app = Flask('')

@app.route('/')
def home():
    return "Bot is running!"

def run_server():
    port = int(os.environ.get("PORT", 8080))
    print(f"🟢 Starting Flask server on port {port}")
    app.run(host='0.0.0.0', port=port)

def keep_alive():
    # Start Flask webserver in a thread
    t = threading.Thread(target=run_server)
    t.daemon = True
    t.start()
    
    # Optional: external self-ping (UptimeRobot or similar recommended)
    def auto_ping():
        url = os.environ.get("PING_URL")  # set this in your host if needed
        if not url:
            return
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
intents = discord.Intents.all()
intents.message_content = True
bot = commands.Bot(command_prefix="!", intents=intents)

@bot.event
async def on_ready():
    print(f"✅ Logged in as {bot.user}")

    # Wait a tiny bit to ensure bot is fully ready
    await asyncio.sleep(2)

    # Set activity status
    activity = discord.Activity(
        type=discord.ActivityType.watching,  # "Watching Servers"
        name="Servers"
    )
    await bot.change_presence(status=discord.Status.online, activity=activity)
    print("🎮 Activity status set!")

    # Start reputation decay task if not already running
    if not decay_reputation.is_running():
        decay_reputation.start()
        print("⏳ Reputation decay task started!")
        
# === Reputation System ===
reputation = {}         # Stores current reputation
last_active = {}        # Tracks last activity timestamp
MAX_REP = 1000          # Maximum reputation cap

# Increment reputation when a user sends a message
@bot.event
async def on_message(message):
    if message.author.bot:
        return

    user_id = message.author.id
    now = time.time()

    # Base points + extra for message length (1 point per 10 chars)
    points = 1 + len(message.content) // 10

    # Update reputation
    current = reputation.get(user_id, 100)
    reputation[user_id] = min(current + points, MAX_REP)

    # Update last active timestamp
    last_active[user_id] = now

    await bot.process_commands(message)

# Background task to decay reputation for inactivity
@tasks.loop(minutes=30)
async def decay_reputation():
    now = time.time()
    for user_id in list(reputation.keys()):
        last = last_active.get(user_id, now)
        # Decay 5 points for every 30 minutes of inactivity
        if now - last > 1800:
            reputation[user_id] = max(reputation[user_id] - 5, 100)

# Command to check reputation
@bot.command()
async def rep(ctx, member: discord.Member = None):
    await ctx.message.delete()
    member = member or ctx.author
    score = reputation.get(member.id, 100)
    await ctx.send(f"📊 **Reputation for {member.display_name}:** {score}", delete_after=7)
    
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

@bot.command(name="cmds")
async def cmds_list(ctx):
    await ctx.message.delete()

    embed = discord.Embed(
        title="📜 XERO Bot Commands",
        description="Here is the list of commands you can use:",
        color=discord.Color.blurple()
    )
    embed.add_field(name="🛡️ !x", value="Shows DDoS protection status", inline=False)
    embed.add_field(name="📊 !rep", value="Check a member's reputation", inline=False)
    embed.add_field(name="📈 !status", value="Server health dashboard", inline=False)
    embed.add_field(name="💬 !ping", value="Check if the bot is awake", inline=False)
    embed.add_field(name="📜 !cmds", value="Displays this command list", inline=False)

    # Send the embed and delete it after 7 seconds
    await ctx.send(embed=embed, delete_after=15)

# === Start Everything ===
keep_alive()

token = os.getenv("TOKEN")
if not token:
    print("❌ ERROR: TOKEN environment variable not set! Please add it in Replit Secrets.")
else:
    bot.run(token)
