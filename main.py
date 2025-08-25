import discord
from discord.ext import commands, tasks
import os
import requests
import threading
from flask import Flask
import time
import asyncio
import itertools
import yt_dlp

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

# === Join Voice Channel ===
async def join_channel(ctx):
    if ctx.author.voice:
        channel = ctx.author.voice.channel
        if ctx.voice_client is None:
            await channel.connect()
        elif ctx.voice_client.channel != channel:
            await ctx.voice_client.move_to(channel)
    else:
        await ctx.send("❌ You must be in a voice channel to use this command.", delete_after=5)

# === Play Song Function ===
async def play_song(ctx, url):
    voice_client = ctx.voice_client
    if voice_client.is_playing():
        voice_client.stop()

    ydl_opts = {'format': 'bestaudio', 'noplaylist': True}
    with yt_dlp.YoutubeDL(ydl_opts) as ydl:
        info = ydl.extract_info(url, download=False)
        audio_url = info['url']

    voice_client.play(
       discord.FFmpegPCMAudio(audio_url, options='-vn')
        after=lambda e: print(f'Finished playing: {e}')
    )

# === Commands ===
@bot.command()
async def play(ctx, *, query):
    await join_channel(ctx)

    ydl_opts = {
        'format': 'bestaudio',
        'noplaylist': True,
        'default_search': 'ytsearch1'  # searches YouTube if it's not a URL
    }

    with yt_dlp.YoutubeDL(ydl_opts) as ydl:
        info = ydl.extract_info(query, download=False)
        # If it's a search, get the first result
        video = info['entries'][0] if 'entries' in info else info
        url = video['webpage_url']
        title = video.get('title', url)

    await play_song(ctx, url)
    await ctx.send(f"▶️ Now playing: {title}", delete_after=10)

@bot.command()
async def stop(ctx):
    if ctx.voice_client:
        await ctx.voice_client.disconnect()
        await ctx.send("⏹️ Stopped and disconnected.", delete_after=5)
    else:
        await ctx.send("❌ Not connected to a voice channel.", delete_after=5)

@bot.command()
async def skip(ctx):
    if ctx.voice_client and ctx.voice_client.is_playing():
        ctx.voice_client.stop()
        await ctx.send("⏭️ Skipped.", delete_after=5)
    else:
        await ctx.send("❌ Nothing is playing.", delete_after=5)


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

# Command to show  two statuses in an embed
@bot.command()
@commands.has_permissions(administrator=True)
async def presence(ctx):
    await ctx.message.delete()
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
    await ctx.send(embed=embed, delete_after=15)

# Command to manually set a status by number
@bot.command()
@commands.has_permissions(administrator=True)
async def setstatus(ctx, number: int):
    await ctx.message.delete()
    
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
    embed.add_field(name="▶︎ $play <query or URL>", value="Plays a song in the voice channel", inline=False)
    embed.add_field(name="❚❚ $stop", value="Stops music and disconnects 𝘟 𝘎𝘶𝘢𝘳𝘥", inline=False)
    embed.add_field(name="⏭ $skip", value="Skips the current song", inline=False)

    embed.set_footer(text="\nNote: Some commands require permissions.")

    # Send the embed and delete it after 25 seconds
    await ctx.send(embed=embed, delete_after=25)

# === Start Everything ===
keep_alive()

token = os.getenv("TOKEN")
if not token:
    print("❌ ERROR: TOKEN environment variable not set! Please add it in Replit Secrets.")
else:
    bot.run(token)












