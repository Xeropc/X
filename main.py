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
import aiohttp

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

# Add this to your moderation commands section
@bot.command()
@commands.has_permissions(manage_messages=True)
async def unmute(ctx, member: discord.Member):
    """Unmute a previously muted member"""
    muted_role = discord.utils.get(ctx.guild.roles, name="Muted")
    
    if not muted_role:
        await ctx.send("❌ There is no Muted role in this server.", delete_after=7)
        return
        
    if muted_role not in member.roles:
        await ctx.send(f"❌ {member.display_name} is not muted.", delete_after=7)
        return
        
    await member.remove_roles(muted_role)
    await ctx.send(f"🔊 Unmuted {member.mention}", delete_after=10)

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

@bot.command()
async def user(ctx, member: discord.Member = None):
    """Display user information"""
    member = member or ctx.author
    await ctx.message.delete()
    
    # Calculate account age
    account_age = (ctx.message.created_at - member.created_at).days
    # Calculate server join age
    join_age = (ctx.message.created_at - member.joined_at).days if member.joined_at else 0
    
    # Get user status
    status = str(member.status).capitalize()
    if member.activity:
        activity = f"Playing {member.activity.name}"
    else:
        activity = "No activity"
    
    # Get user roles (excluding @everyone)
    roles = [role.mention for role in member.roles if role.name != "@everyone"]
    if not roles:
        roles = ["No roles"]
    
    # Create embed
    embed = discord.Embed(
        title=f"👤 User Information - {member.display_name}",
        color=member.color
    )
    
    # Add fields
    embed.add_field(name="📛 Username", value=f"{member.name}#{member.discriminator}", inline=True)
    embed.add_field(name="🆔 User ID", value=member.id, inline=True)
    embed.add_field(name="📊 Reputation", value=reputation.get(member.id, 100), inline=True)
    
    embed.add_field(name="📅 Account Created", value=f"{member.created_at.strftime('%b %d, %Y')}\n({account_age} days ago)", inline=True)
    
    if member.joined_at:
        embed.add_field(name="📥 Joined Server", value=f"{member.joined_at.strftime('%b %d, %Y')}\n({join_age} days ago)", inline=True)
    else:
        embed.add_field(name="📥 Joined Server", value="Unknown", inline=True)
    
    embed.add_field(name="🎭 Highest Role", value=member.top_role.mention, inline=True)
    
    embed.add_field(name="🟢 Status", value=status, inline=True)
    embed.add_field(name="🎮 Activity", value=activity, inline=True)
    embed.add_field(name="📋 Roles", value=" ".join(roles[:3]) + (f" (+{len(roles)-3} more)" if len(roles) > 3 else ""), inline=False)
    
    # Add avatar thumbnail
    if member.avatar:
        embed.set_thumbnail(url=member.avatar.url)
    
    embed.set_footer(text=f"Requested by {ctx.author.display_name}", icon_url=ctx.author.avatar.url if ctx.author.avatar else None)
    
    await ctx.send(embed=embed, delete_after=30)

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
async def caseoh(ctx):
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
async def cmds_list(ctx, page: int = 1):
    await ctx.message.delete()
    
    # Define pages
    pages = [
        {
            "title": "📜 XERO Bot Commands - Page 1/3",
            "description": "General Commands",
            "fields": [
                ("⛉ $x", "Shows DDoS protection status", False),
                ("✦ $rep [user]", "Check a member's reputation", False),
                ("✚ $status", "Server health dashboard", False),
                ("𝗓𐰁 $ping", "Check if the bot is awake", False),
                ("𝗓𐰁 $user [user]", "View user details", False),
                ("☰ $cmds [page]", "Displays this command list", False),
            ],
            "restricted": False
        },
        {
            "title": "📜 XERO Bot Commands - Page 2/3",
            "description": "Entertainment Commands",
            "fields": [
                ("🎭 $joke", "Tell a random joke", False),
                ("🪙 $coinflip", "Flip a coin", False),
                ("🎲 $dice [sides]", "Roll a dice (default 6 sides)", False),
                ("📸 $meme", "Get a random meme", False)
            ],
            "restricted": False
        },
        {
            "title": "🔒 ADMIN ONLY COMMANDS - Page 3/3",
            "description": "**Administrator Permissions Required**",
            "fields": [
                ("✗ $presence", "Change status of 𝘟 𝘎𝘶𝘢𝘳𝘥", False),
                ("☣︎ $purge [amount]", "Purge messages", False),
                ("🛡️ $ban @user [reason]", "Ban a member", False),
                ("👢 $kick @user [reason]", "Kick a member", False),
                ("🔇 $mute @user [minutes]", "Temporarily mute a member", False),
                ("🔊 $unmute @user", "Unmute a muted member", False),
                ("⚙️ $setstatus [number]", "Set bot status manually", False),
            ],
            "restricted": True
        }
    ]
    
    # Validate page number
    if page < 1 or page > len(pages):
        page = 1
    
    # Check if user is trying to access restricted page without permissions
    if pages[page-1]["restricted"] and not ctx.author.guild_permissions.administrator:
        # Show permission required message instead of the admin page
        embed = discord.Embed(
            title="🔒 ADMIN COMMANDS - Page 3/3",
            description="**Administrator Permissions Required**\n\nYou need the Administrator permission to view this page.",
            color=discord.Color.red()
        )
        embed.set_footer(text="Page 3/3 • React with ◀️ to go back")
        
        message = await ctx.send(embed=embed)
        
        # Only add back arrow
        await message.add_reaction("◀️")
        
        # Wait for reaction input
        def check(reaction, user):
            return user == ctx.author and str(reaction.emoji) == "◀️" and reaction.message.id == message.id
        
        try:
            reaction, user = await bot.wait_for("reaction_add", timeout=15.0, check=check)
            await message.delete()
            await cmds_list(ctx, page=2)  # Go back to page 2
        except asyncio.TimeoutError:
            try:
                await message.clear_reactions()
            except:
                pass
        return
    
    current_page = pages[page-1]
    
    embed = discord.Embed(
        title=current_page["title"],
        description=current_page["description"],
        color=discord.Color.blurple() if not current_page["restricted"] else discord.Color.gold()
    )
    
    for name, value, inline in current_page["fields"]:
        embed.add_field(name=name, value=value, inline=inline)
    
    embed.set_footer(text=f"Page {page}/{len(pages)} • React with ◀️ ▶️ to navigate")
    
    # Send the embed
    message = await ctx.send(embed=embed)
    
    # Add reactions for navigation if there are multiple pages
    if len(pages) > 1:
        # Only add left arrow if not on first page
        if page > 1:
            await message.add_reaction("◀️")
        
        # Only add right arrow if not on last page and has permissions for next page
        if page < len(pages):
            next_page_restricted = pages[page]["restricted"]
            has_permissions = not next_page_restricted or ctx.author.guild_permissions.administrator
            
            if has_permissions:
                await message.add_reaction("▶️")
            else:
                # User doesn't have permissions for next page, don't show arrow
                pass
        
        # Wait for reaction input
        def check(reaction, user):
            return user == ctx.author and str(reaction.emoji) in ["◀️", "▶️"] and reaction.message.id == message.id
        
        try:
            reaction, user = await bot.wait_for("reaction_add", timeout=30.0, check=check)
            
            if str(reaction.emoji) == "▶️" and page < len(pages):
                await message.delete()
                await cmds_list(ctx, page + 1)
            elif str(reaction.emoji) == "◀️" and page > 1:
                await message.delete()
                await cmds_list(ctx, page - 1)
                
        except asyncio.TimeoutError:
            try:
                await message.clear_reactions()
            except:
                pass  # Ignore if message was already deleted

# === Start Everything ===
keep_alive()

token = os.getenv("TOKEN")
if not token:
    print("❌ ERROR: TOKEN environment variable not set! Please add it in Replit Secrets.")
else:
    bot.run(token)
