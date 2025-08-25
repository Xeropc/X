import discord
from discord.ext import commands, tasks
import os
import requests
import threading
from flask import Flask
import time
import asyncio
import itertools
import random

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
bot = commands.Bot(command_prefix="$", intents=intents)

# List of statuses for embeds / manual selection
statuses_list = [
    discord.Streaming(name="X", url="https://www.twitch.tv/error"),
    discord.Activity(type=discord.ActivityType.watching, name="Servers"),
]

# Cycle through statuses automatically
statuses = itertools.cycle(statuses_list)

@bot.event
async def on_ready():
    print(f"✅ Logged in as {bot.user}")
    await asyncio.sleep(2)  # tiny wait to avoid race conditions
    change_status.start()

@tasks.loop(minutes=22)  # changes every 22 minutes
async def change_status():
    await bot.change_presence(activity=next(statuses))
        
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

# === Advanced Moderation ===
@bot.command()
@commands.has_permissions(ban_members=True)
async def ban(ctx, member: discord.Member, *, reason="No reason provided"):
    """Ban a member from the server"""
    await member.ban(reason=reason)
    await ctx.send(f"✅ Banned {member.mention} | Reason: {reason}", delete_after=10)

@bot.command()
@commands.has_permissions(kick_members=True)
async def kick(ctx, member: discord.Member, *, reason="No reason provided"):
    """Kick a member from the server"""
    await member.kick(reason=reason)
    await ctx.send(f"✅ Kicked {member.mention} | Reason: {reason}", delete_after=10)

@bot.command()
@commands.has_permissions(manage_messages=True)
async def mute(ctx, member: discord.Member, duration: int = 10):
    """Temporarily mute a member (in minutes)"""
    muted_role = discord.utils.get(ctx.guild.roles, name="Muted")
    if not muted_role:
        muted_role = await ctx.guild.create_role(name="Muted")
        for channel in ctx.guild.channels:
            await channel.set_permissions(muted_role, send_messages=False)
    
    await member.add_roles(muted_role)
    await ctx.send(f"🔇 Muted {member.mention} for {duration} minutes", delete_after=10)
    
    # Auto-unmute after duration
    await asyncio.sleep(duration * 60)
    await member.remove_roles(muted_role)

# Command to show  two statuses in an embed
@bot.command()
@commands.has_permissions(administrator=True)
async def presence(ctx):
    embed = discord.Embed(
        title="Presence Manager",
        description="Select a status to set",
        color=discord.Color.blurple()
    )

    # Show statuses without URL in the embed
    for i, s in enumerate(statuses_list, start=1):
        if isinstance(s, discord.Streaming):
            type_name = "Streaming"
            value = s.name  # just show the name, hide URL
        else:
            type_name = s.type.name.capitalize()
            value = s.name
        embed.add_field(name=f"{i}. {type_name}", value=value, inline=False)

    embed.set_footer(text="Use $setstatus <number> to change status.")
    await ctx.send(embed=embed, delete_after=10)

# Command to manually set a status by number
@bot.command()
@commands.has_permissions(administrator=True)
async def setstatus(ctx, number: int):
    if 1 <= number <= len(statuses_list):
        activity = statuses_list[number - 1]
        await bot.change_presence(activity=activity)
        await ctx.send(
            f"✅ Status changed to: **{getattr(activity, 'name', 'Unknown')}**",
            delete_after=7  # <-- deletes after 7 seconds
        )

        # Reset the cycle so the next automatic update continues from the next status
        global statuses
        new_order = statuses_list[number:] + statuses_list[:number-1]
        statuses = itertools.cycle(new_order)

    else:
        await ctx.send(
            "❌ Invalid status number.",
            delete_after=7  # <-- also deletes after 7 seconds
        )

@bot.command()
@commands.has_permissions(administrator=True)
async def purge(ctx, amount: int = 100):
    """
    Purges messages in the current channel.
    amount: Number of messages to delete (default 100)
    """
    # Purge the specified number of messages INCLUDING the command message itself
    deleted = await ctx.channel.purge(limit=amount + 1)  # +1 to include the $purge command
    
    # Optional: send a quick confirmation message and delete it immediately
    confirm_msg = await ctx.send(f"Deleted {len(deleted)-1} messages.")  # exclude the command itself
    await confirm_msg.delete(delay=0)  # delete immediately

@bot.command()
async def quote(ctx):
    """Get a random Caseoh quote"""
    await ctx.message.delete()
    
    quotes = [
        "Life. - Caseoh",
        "Ellen, what did i tell you comin back to this STORE.",
        "You goobers in the chat just say DOOR, DOOR, DOOR hululu",
        "TIM IM GON KILL YOU (#code Caseoh StarforgeSystems.com for 10% off! :D)",
        "Use cheeky hashtag code Caseoh for 10% off - Caseoh", 
        "STARFORGESYSTEMS.COM - Caseoh",
        "Dagum disgusting putrid loser - Caseoh",
        "Just chill out and vibe. That's life right there. - Caseoh",
        "As long as you don't know what's under the surface, you're good. - Caseoh",
        "Door. - Caseoh",
        "I'm not fat, I'm just big boneded. - Caseoh",
        "Chat, I will end you. - Caseoh",
        "This is why we can't have nice things. - Caseoh",
        "You're actually disgusting. - Caseoh",
        "I'm gonna scream. - Caseoh"
    ]
    
    # Ensure proper randomness
    selected_quote = random.choice(quotes)
    print(f"Selected quote: {selected_quote}")  # ← MOVE THE PRINT STATEMENT HERE
    
    # Use an embed for better formatting
    embed = discord.Embed(
        title="💬 Caseoh Quote",
        description=selected_quote,
        color=discord.Color.gold()
    )
    embed.set_footer(text="Inspirational wisdom from Caseoh")
    
    await ctx.send(embed=embed, delete_after=25)

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
    embed.add_field(name="⛉ $x", value="Shows DDoS protection status", inline=False)
    embed.add_field(name="✦ $rep", value="Check a member's reputation", inline=False)
    embed.add_field(name="✚ $status", value="Server health dashboard", inline=False)
    embed.add_field(name="𝗓𐰁 $ping", value="Check if the bot is awake", inline=False)
    embed.add_field(name="☰ $cmds", value="Displays this command list", inline=False)
    embed.add_field(name="✗ $presence", value="Change status of 𝘟 𝘎𝘶𝘢𝘳𝘥 (Permission Required)", inline=False)
    embed.add_field(name="☣︎ $purge", value="Purge's messages (Permission Required)", inline=False)
    embed.set_footer(text="Note: Some commands require permissions.")

    # Send the embed and delete it after 25 seconds
    await ctx.send(embed=embed, delete_after=25)

# === Start Everything ===
keep_alive()

token = os.getenv("TOKEN")
if not token:
    print("❌ ERROR: TOKEN environment variable not set! Please add it in Replit Secrets.")
else:
    bot.run(token)



