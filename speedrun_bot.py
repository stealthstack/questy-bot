import discord
import json
import os
import random
import requests
import re
from io import BytesIO
from PIL import Image
from discord.ext import commands
from datetime import datetime, date, timedelta
from collections import Counter
import asyncio
import logging
from dotenv import load_dotenv

load_dotenv()

# Load your speedrun data
with open('speedrun_data.json', 'r', encoding='utf-8') as f:
    SPEEDRUN_DB = json.load(f)

# Stone image file mapping
STONE_FILES = {
    "WL": "images/waitlessstone.png",
    "WW": "images/whackwhackstone.png",
    "BB": "images/broadburststone.png",
    "Sc": "images/scattershotstone.png",
    "Sh": "images/sharingstone.png",
    "Stay Strong Stone": "images/staystrongstone.png"
}

# Available items for expedition rewards
ITEMS = list(STONE_FILES.keys())

# Global dictionary to track active expeditions
active_expeditions = {}  # channel_id: Expedition

# Set up logger
logger = logging.getLogger('speedrun_bot')
logger.setLevel(logging.INFO)
handler = logging.StreamHandler()
formatter = logging.Formatter('%(asctime)s - %(levelname)s - %(message)s')
handler.setFormatter(formatter)
logger.addHandler(handler)

# Helper functions to reduce duplicate code

def create_composite_image(images, filename, gap=0):
    """Create a composite image from a list of PIL images and return as discord.File"""
    if not images:
        return None, None

    total_width = sum(img.width for img in images) + (len(images) - 1) * gap
    max_height = max(img.height for img in images)
    composite = Image.new('RGBA', (total_width, max_height))
    x_offset = 0
    for i, img in enumerate(images):
        composite.paste(img, (x_offset, 0))
        x_offset += img.width
        if i < len(images) - 1:
            x_offset += gap

    io_obj = BytesIO()
    composite.save(io_obj, format='PNG')
    io_obj.seek(0)
    file_obj = discord.File(io_obj, filename=filename)
    return file_obj, composite

def create_record_embed(record):
    """Create a full record embed with composite stones image and thumbnail"""
    # Status indicator
    status_emoji = "🏆" if record['status'] == 'WR' else "🔥" if record['status'] == 'PB' else "📜"

    # Pokémon emoji mapping
    pokemon_emojis = {
        "Hitmonlee": "👊", "Weepinbell": "🌿", "Machop": "💪",
        "Victreebell": "🍃", "Machamp": "💥", "": "❓"
    }
    pokemon_emoji = pokemon_emojis.get(record['pokemon'].strip(), "🔹")

    # Category colors
    category_colors = {
        "12-Boss": discord.Color.blue(),
        "12B-no-buffer": discord.Color.red(),
        "12B-solo": discord.Color.green(),
        "Any%": discord.Color.gold(),
        "Any%-DLC": discord.Color.purple()
    }

    embed = discord.Embed(
        title=f"{pokemon_emoji} {record['runner']}'s {record['pokemon']}",
        description=f"**{record['category']}** • Time: `{record['time']}`s • **IV:** {record['overall_iv']} • **Status:** {status_emoji} {record['status']}",
        color=category_colors.get(record['category'], discord.Color.default())
    )

    # Create composite stone image
    files = []
    stone_images = []
    for s in record['move_stones']:
        if s:
            file_path = STONE_FILES.get(s)
            if file_path:
                try:
                    img = Image.open(file_path)
                    img = img.resize((32, 32))
                    stone_images.append(img)
                except:
                    placeholder = Image.new('RGBA', (32, 32), (128, 128, 128, 255))
                    stone_images.append(placeholder)
            else:
                placeholder = Image.new('RGBA', (32, 32), (128, 128, 128, 255))
                stone_images.append(placeholder)
        else:
            placeholder = Image.new('RGBA', (32, 32), (200, 200, 200, 255))
            stone_images.append(placeholder)

    if stone_images:
        stones_file, _ = create_composite_image(stone_images, 'stones.png')
        if stones_file:
            files.append(stones_file)
            embed.set_image(url="attachment://stones.png")

    # Stats
    embed.add_field(name="⚔️ Stats", value=f"ATK: **{record['atk_total']}** / HP: **{record['hp']}**", inline=True)

    # Bingo bonuses
    valid_bingos = [b for b in record['bingo_bonuses'] if b and b != '—']
    if valid_bingos:
        bingo_text = ' | '.join(valid_bingos)
        embed.add_field(name="🎯 Bingo Bonuses", value=bingo_text[:100] + ("..." if len(bingo_text) > 100 else ""), inline=False)

    # Video link
    embed.add_field(name="📺 Watch Run", value=f"[YouTube Link]({record['video_link']})", inline=False)

    # Footer
    embed.set_footer(text=f"Runner: {record['runner']} • Data from Pokemon Quest Speedrun Community")

    # Thumbnail
    pokemon_thumbnails = {
        "Hitmonlee": "images/106.png",
        "Weepinbell": "images/070.png",
        "Machop": "images/066.png",
        "Victreebell": "images/071.png",
    }
    thumbnail_path = pokemon_thumbnails.get(record['pokemon'].strip(), "images/controller.png")
    embed.set_thumbnail(url=f"attachment://{thumbnail_path.split('/')[-1]}")
    try:
        with open(thumbnail_path, 'rb') as f:
            thumbnail_file = discord.File(f, filename=thumbnail_path.split('/')[-1])
            files.append(thumbnail_file)
    except:
        pass

    return embed, files

def create_expedition_results_embed(results, ctx):
    """Create expedition results embed"""
    embed = discord.Embed(title="Expedition Results", color=discord.Color.green())
    for user_id, result in results.items():
        user_id_str = str(user_id)
        name = f"Dummy {user_id_str.split('_')[1]}" if user_id_str.startswith("dummy_") else (ctx.guild.get_member(user_id).display_name if ctx.guild.get_member(user_id) else "Unknown")
        embed.add_field(name=name, value=f"Success: {result['success']}, Damage: {result['damage']}, Time: {result['time']:.1f}s", inline=False)
    return embed

class Expedition:
    def __init__(self, channel_id, leader_id):
        self.channel_id = channel_id
        self.leader_id = leader_id
        self.participants = {}  # user_id: pokemon_record
        self.phase = "preparation"  # preparation, battle, results
        self.start_time = None
        self.battle_end_time = None
        self.results = {}
        self.message = None  # Reference to the expedition embed message
        # Select 3 random Pokémon for the expedition
        self.expedition_pokemon = [random.choice(SPEEDRUN_DB) for _ in range(3)]
        # Add leader with random pokemon
        record = random.choice(SPEEDRUN_DB)
        self.participants[leader_id] = {"ready": True, "pokemon": record}

    async def add_participant(self, user_id):
        if self.phase != "preparation":
            return False, False  # Cannot add participants after preparation phase
        if user_id not in self.participants:
            record = random.choice(SPEEDRUN_DB)
            self.participants[user_id] = {"ready": True, "pokemon": record}
            # Check if we have 3 participants now
            if len(self.participants) == 3:
                await self.start_battle()
                return True, True  # added, started_battle
            return True, False  # added, not started
        return False, False  # not added, not started

    async def remove_participant(self, user_id):
        if user_id in self.participants and user_id != self.leader_id:
            del self.participants[user_id]
            return True
        return False

    async def set_ready(self, user_id, pokemon_record):
        if user_id in self.participants:
            self.participants[user_id]["ready"] = True
            self.participants[user_id]["pokemon"] = pokemon_record
            return True
        return False

    async def start_battle(self):
        if all(p["ready"] for p in self.participants.values()):
            self.phase = "battle"
            self.start_time = datetime.now()
            self.battle_end_time = self.start_time  # Immediate results
            # Simulate battle results
            for user_id in self.participants:
                # Random battle outcome
                success = random.choice([True, False])
                self.results[user_id] = {
                    "success": success,
                    "damage": random.randint(100, 1000) if success else 0,
                    "time": random.uniform(60, 300)  # 1-5 minutes
                }
            return True
        return False

    async def get_results(self):
        if self.phase == "results":
            return self.results
        if self.phase == "battle" and datetime.now() >= self.battle_end_time:
            self.phase = "results"
            return self.results
        return None

    async def set_results(self, results_string):
        """Parse and set expedition results from user input string"""
        # Expected format: "Questy APP — 1:51 PM Expedition Results Unknown Success: True, Damage: 239, Time: 271.0s Dummy 1 Success: False, Damage: 0, Time: 158.8s Dummy 2 Success: False, Damage: 0, Time: 201.5s"
        # Replace "Unknown" with the actual player name, but since it's submitted by the player, assume the first is the player
        lines = results_string.strip().split('\n')
        if not lines:
            return False

        # Parse each line
        parsed_results = {}
        for line in lines:
            line = line.strip()
            if not line:
                continue
            # Match patterns like "Questy APP Success: True, Damage: 239, Time: 271.0s"
            match = re.match(r"(.+?) Success: (True|False), Damage: (\d+), Time: ([\d.]+)s", line)
            if match:
                name = match.group(1).strip()
                success = match.group(2) == "True"
                damage = int(match.group(3))
                time = float(match.group(4))
                parsed_results[name] = {
                    "success": success,
                    "damage": damage,
                    "time": time
                }

        if not parsed_results:
            return False

        # Map to participants: assume the first non-dummy is the player, dummies are dummies
        self.results = {}
        player_found = False
        for user_id, data in self.participants.items():
            user_id_str = str(user_id)
            if user_id_str.startswith("dummy_"):
                dummy_num = int(user_id_str.split('_')[1])
                dummy_key = f"Dummy {dummy_num}"
                if dummy_key in parsed_results:
                    self.results[user_id] = parsed_results[dummy_key]
            else:
                if not player_found:
                    # Find the player name in parsed_results, assuming it's not Dummy
                    for name, result in parsed_results.items():
                        if not name.startswith("Dummy"):
                            self.results[user_id] = result
                            player_found = True
                            break
                if not player_found:
                    # Fallback, use first non-dummy
                    for name, result in parsed_results.items():
                        if not name.startswith("Dummy"):
                            self.results[user_id] = result
                            break

        self.phase = "results"
        return True

# ✅ CRITICAL: Enable message content intent properly
intents = discord.Intents.default()
intents.message_content = True  # This reads "!commands"
intents.messages = True  # This allows reading messages

bot = commands.Bot(
    command_prefix='!',
    intents=intents,
    help_command=None  # Optional: removes default !help
)

@bot.event
async def on_ready():
    print(f'✅ Bot is online as {bot.user}')
    print(f'🆔 Bot ID: {bot.user.id}')
    print('🔧 Commands: !speedrun, !dailypot, !devpot, !collection, !expedition, !submitresults, !storage, !ping')

@bot.command(name='speedrun')
async def show_speedrun(ctx, category: str = None):
    """Display a random speedrun record, optionally filtered by category"""
    try:
        # Filter by category if provided
        if category:
            available_categories = set(r['category'] for r in SPEEDRUN_DB)
            # Find closest match (case-insensitive)
            matched_category = next(
                (c for c in available_categories if category.lower() in c.lower()),
                None
            )

            if not matched_category:
                await ctx.send(f"❌ Category not found. Available: {', '.join(available_categories)}")
                return

            filtered_runs = [r for r in SPEEDRUN_DB if r['category'].lower() == matched_category.lower()]
            if not filtered_runs:
                await ctx.send(f"❌ No runs found for category: {matched_category}")
                return

            record = random.choice(filtered_runs)
        else:
            record = random.choice(SPEEDRUN_DB)

        embed, files = create_record_embed(record)
        await ctx.send(embed=embed, files=files)

    except Exception as e:
        await ctx.send(f"❌ Error: {e}")
        print(f"Error: {e}")

# Simple test command
@bot.command(name='ping')
async def ping(ctx):
    """Check if bot is responsive"""
    await ctx.send(f'🏓 Pong! Latency: {round(bot.latency * 1000)}ms')

@bot.command(name='storage')
async def storage(ctx):
    """Display available items (stones)"""
    try:
        embed = discord.Embed(
            title="📦 Available Items",
            description="Here are the available stones you can use:",
            color=discord.Color.blue()
        )

        # Create composite stone image
        files = []
        stone_images = []
        for stone in ITEMS:
            file_path = STONE_FILES.get(stone)
            if file_path:
                try:
                    img = Image.open(file_path)
                    img = img.resize((64, 64))
                    stone_images.append(img)
                except:
                    placeholder = Image.new('RGBA', (64, 64), (128, 128, 128, 255))
                    stone_images.append(placeholder)
            else:
                placeholder = Image.new('RGBA', (64, 64), (128, 128, 128, 255))
                stone_images.append(placeholder)

        # Composite horizontally with gaps
        if stone_images:
            gap = 10
            total_width = sum(img.width for img in stone_images) + (len(stone_images) - 1) * gap
            max_height = max(img.height for img in stone_images)
            composite = Image.new('RGBA', (total_width, max_height))
            x_offset = 0
            for i, img in enumerate(stone_images):
                composite.paste(img, (x_offset, 0))
                x_offset += img.width
                if i < len(stone_images) - 1:
                    x_offset += gap

            stones_io = BytesIO()
            composite.save(stones_io, format='PNG')
            stones_io.seek(0)
            stones_file = discord.File(stones_io, filename='storage_stones.png')
            files.append(stones_file)

            embed.set_image(url="attachment://storage_stones.png")

        # List the stones
        stones_text = '\n'.join(f"• {stone}" for stone in ITEMS)
        embed.add_field(name="Stones", value=stones_text, inline=False)

        embed.set_footer(text="These stones can be used in expeditions and other features.")

        await ctx.send(embed=embed, files=files)

    except Exception as e:
        await ctx.send(f"❌ Error: {e}")
        print(f"Error: {e}")

@bot.command(name='expedition')
async def expedition(ctx):
    """Start or join an expedition in this channel"""
    channel_id = str(ctx.channel.id)
    user_id = ctx.author.id

    if channel_id in active_expeditions:
        expedition = active_expeditions[channel_id]
        if user_id not in expedition.participants:
            added, started_battle = await expedition.add_participant(user_id)
            if added:
                if expedition.message:
                    # Edit the existing embed
                    embed = create_expedition_embed(expedition)
                    view = ExpeditionView(expedition, ctx)
                    await expedition.message.edit(embed=embed, view=view)
                    view.message = expedition.message
                else:
                    await send_expedition_embed(ctx, expedition)

        else:
            await ctx.send(f"{ctx.author.mention} is already in the expedition!")
    else:
        expedition = Expedition(channel_id, user_id)
        active_expeditions[channel_id] = expedition
        await ctx.send(f"{ctx.author.mention} started a new expedition!")
        # Send the expedition embed
        await send_expedition_embed(ctx, expedition)

@bot.command(name='submitresults')
async def submit_results(ctx, *, results_string):
    """Submit expedition results (leader only)"""
    channel_id = str(ctx.channel.id)

    if channel_id not in active_expeditions:
        await ctx.send("❌ No active expedition in this channel.")
        return

    expedition = active_expeditions[channel_id]

    if expedition.phase != "battle":
        await ctx.send("❌ Expedition is not in battle phase.")
        return

    if str(ctx.author.id) != str(expedition.leader_id):
        await ctx.send("❌ Only the expedition leader can submit results.")
        return

    success = await expedition.set_results(results_string)

    if not success:
        await ctx.send("❌ Failed to parse results. Please check the format. Expected: 'Name Success: True/False, Damage: X, Time: Ys' per line.")
        return

    # Send results embed
    results = await expedition.get_results()
    if results:
        embed = discord.Embed(title="Expedition Results", color=discord.Color.green())
        for user_id, result in results.items():
            user_id_str = str(user_id)
            name = f"Dummy {user_id_str.split('_')[1]}" if user_id_str.startswith("dummy_") else (ctx.guild.get_member(user_id).display_name if ctx.guild.get_member(user_id) else "Unknown")
            embed.add_field(name=name, value=f"Success: {result['success']}, Damage: {result['damage']}, Time: {result['time']:.1f}s", inline=False)
        await ctx.send(embed=embed)
        # Remove expedition
        del active_expeditions[channel_id]
    else:
        await ctx.send("❌ No results available.")

def create_expedition_embed(expedition):
    embed = discord.Embed(title="Expedition", description=f"Phase: {expedition.phase}", color=discord.Color.blue())
    expedition_pokemon_text = ", ".join([p['pokemon'] for p in expedition.expedition_pokemon])
    embed.add_field(name="Expedition Pokémon", value=expedition_pokemon_text, inline=False)
    participants_text = ""
    for user_id, data in expedition.participants.items():
        ready = "Ready" if data["ready"] else "Not Ready"
        pokemon = data["pokemon"]["pokemon"] if data["pokemon"] else "None"
        user_id_str = str(user_id)
        name = f"Dummy {user_id_str.split('_')[1]}" if user_id_str.startswith("dummy_") else f"<@{user_id_str}>"
        participants_text += f"{name}: {ready}, Pokemon: {pokemon}\n"
    embed.add_field(name="Participants", value=participants_text or "None", inline=False)
    return embed

async def send_expedition_embed(ctx, expedition):
    embed = create_expedition_embed(expedition)
    view = ExpeditionView(expedition, ctx)
    message = await ctx.send(embed=embed, view=view)
    expedition.message = message
    view.message = message

class ExpeditionView(discord.ui.View):
    def __init__(self, expedition, ctx):
        super().__init__(timeout=300)
        self.expedition = expedition
        self.ctx = ctx
        self.dummy_counter = 1

        # Add Join button for all users
        join_button = discord.ui.Button(label="Join", style=discord.ButtonStyle.primary)
        join_button.callback = self.join
        self.add_item(join_button)

        # Add Leave button for participants (not leader)
        leave_button = discord.ui.Button(label="Leave", style=discord.ButtonStyle.secondary)
        leave_button.callback = self.leave
        self.add_item(leave_button)

        # Add Ready button for participants
        ready_button = discord.ui.Button(label="Ready", style=discord.ButtonStyle.success)
        ready_button.callback = self.ready
        self.add_item(ready_button)

        # Add Start Battle button only for leader
        if str(self.ctx.author.id) == str(expedition.leader_id):
            start_button = discord.ui.Button(label="Start Battle", style=discord.ButtonStyle.danger)
            start_button.callback = self.start_battle
            self.add_item(start_button)

        # Add Add Dummy button only for dev user
        if str(expedition.leader_id) == "205180213384970240":
            add_dummy_button = discord.ui.Button(label="Add Dummy", style=discord.ButtonStyle.secondary)
            add_dummy_button.callback = self.add_dummy
            self.add_item(add_dummy_button)

    async def on_timeout(self):
        # Remove expedition if it hasn't started
        if self.expedition.phase == "preparation":
            if self.expedition.channel_id in active_expeditions:
                del active_expeditions[self.expedition.channel_id]
            # Optionally disable buttons or update embed, but since it's timed out, no need

    async def join(self, interaction):
        user_id = interaction.user.id
        if await self.expedition.add_participant(user_id):
            await interaction.response.send_message(f"{interaction.user.mention} joined the expedition!", ephemeral=True)
            await self.update_embed()
        else:
            await interaction.response.send_message("Already in expedition!", ephemeral=True)

    async def leave(self, interaction):
        user_id = interaction.user.id
        if await self.expedition.remove_participant(user_id):
            await interaction.response.send_message(f"{interaction.user.mention} left the expedition!", ephemeral=True)
            await self.update_embed()
        else:
            await interaction.response.send_message("Cannot leave!", ephemeral=True)

    async def ready(self, interaction):
        user_id = interaction.user.id
        # Pick a random pokemon for simplicity
        record = random.choice(SPEEDRUN_DB)
        if await self.expedition.set_ready(user_id, record):
            await interaction.response.send_message(f"{interaction.user.mention} is ready!", ephemeral=True)
            await self.update_embed()
        else:
            await interaction.response.send_message("Not in expedition!", ephemeral=True)

    async def start_battle(self, interaction):
        if interaction.user.id == self.expedition.leader_id:
            if await self.expedition.start_battle():
                await interaction.response.send_message("Battle started!", ephemeral=False)
                # Start a task to check for results
                self.ctx.bot.loop.create_task(self.check_results())
            else:
                await interaction.response.send_message("Not all ready!", ephemeral=True)
        else:
            await interaction.response.send_message("Only leader can start!", ephemeral=True)

    async def add_dummy(self, interaction):
        dummy_id = f"dummy_{self.dummy_counter}"
        await self.expedition.add_participant(dummy_id)
        self.dummy_counter += 1
        await interaction.response.send_message(f"Added dummy participant!", ephemeral=False)
        await self.update_embed()

    async def update_embed(self):
        embed = create_expedition_embed(self.expedition)
        # Disable buttons if phase is not preparation
        if self.expedition.phase != "preparation":
            for child in self.children:
                child.disabled = True
        await self.message.edit(embed=embed, view=self)

    async def check_results(self):
        # Check immediately for results
        results = await self.expedition.get_results()
        if results:
            # Send results embed
            embed = discord.Embed(title="Expedition Results", color=discord.Color.green())
            for user_id, result in results.items():
                user_id_str = str(user_id)
                name = f"Dummy {user_id_str.split('_')[1]}" if user_id_str.startswith("dummy_") else (self.ctx.guild.get_member(user_id).display_name if self.ctx.guild.get_member(user_id) else "Unknown")
                embed.add_field(name=name, value=f"Success: {result['success']}, Damage: {result['damage']}, Time: {result['time']:.1f}s", inline=False)
            await self.ctx.send(embed=embed)
            # Remove expedition
            del active_expeditions[self.expedition.channel_id]
        else:
            # If no results yet, wait 5 minutes and check again
            await asyncio.sleep(300)
            results = await self.expedition.get_results()
            if results:
                # Send results embed
                embed = discord.Embed(title="Expedition Results", color=discord.Color.green())
                for user_id, result in results.items():
                    user_id_str = str(user_id)
                    name = f"Dummy {user_id_str.split('_')[1]}" if user_id_str.startswith("dummy_") else (self.ctx.guild.get_member(user_id).display_name if self.ctx.guild.get_member(user_id) else "Unknown")
                    embed.add_field(name=name, value=f"Success: {result['success']}, Damage: {result['damage']}, Time: {result['time']:.1f}s", inline=False)
                await self.ctx.send(embed=embed)
                # Remove expedition
                del active_expeditions[self.expedition.channel_id]

@bot.command(name='collection')
async def show_collection(ctx, index: int = None):
    """Display the user's claimed speedrun Pokémon collection or a specific entry by index"""
    try:
        # Load claims data
        try:
            with open('daily_pot_claims.json', 'r') as f:
                claims = json.load(f)
        except FileNotFoundError:
            claims = {}

        user_id = str(ctx.author.id)
        if user_id not in claims or not claims[user_id].get("collection"):
            await ctx.send("❌ You haven't claimed any Pokémon from the daily pot yet! Use `!dailypot` to start collecting.")
            return

        collection = claims[user_id]["collection"]
        total_claims = len(collection)

        # Sort collection by fastest times (ascending), then by runner name (ascending)
        collection = sorted(collection, key=lambda r: (float(r['time']), r['runner']))

        # Group records by unique entries and count occurrences
        def make_hashable(record):
            return tuple(sorted((k, tuple(v) if isinstance(v, list) else v) for k, v in record.items()))

        record_counts = Counter(make_hashable(record) for record in collection)
        unique_records = list(record_counts.keys())

        # Sort unique records by time and runner
        unique_records.sort(key=lambda h: (float(dict(h)['time']), dict(h)['runner']))

        if index is not None:
            # Show specific entry
            if not (1 <= index <= len(unique_records)):
                await ctx.send(f"❌ Invalid index. You have {len(unique_records)} unique Pokémon in your collection.")
                return

            record_hash = unique_records[index - 1]
            record = dict(record_hash)

            # Status indicator
            status_emoji = "🏆" if record['status'] == 'WR' else "🔥" if record['status'] == 'PB' else "📜"

            # Pokémon emoji mapping
            pokemon_emojis = {
                "Hitmonlee": "👊", "Weepinbell": "🌿", "Machop": "💪",
                "Victreebell": "🍃", "Machamp": "💥", "": "❓"
            }
            pokemon_emoji = pokemon_emojis.get(record['pokemon'].strip(), "🔹")

            # Create the card with category badge
            category_colors = {
                "12-Boss": discord.Color.blue(),
                "12B-no-buffer": discord.Color.red(),
                "12B-solo": discord.Color.green(),
                "Any%": discord.Color.gold(),
                "Any%-DLC": discord.Color.purple()
            }

            embed = discord.Embed(
                title=f"{pokemon_emoji} {record['runner']}'s {record['pokemon']}",
                description=f"**{record['category']}** • Time: `{record['time']}`s • **IV:** {record['overall_iv']} • **Status:** {status_emoji} {record['status']}",
                color=category_colors.get(record['category'], discord.Color.default())
            )

            # Create composite stone image
            files = []
            stone_images = []
            for s in record['move_stones']:
                if s:
                    file_path = STONE_FILES.get(s)
                    if file_path:
                        try:
                            img = Image.open(file_path)
                            img = img.resize((32, 32))
                            stone_images.append(img)
                        except:
                            # Placeholder for error
                            placeholder = Image.new('RGBA', (32, 32), (128, 128, 128, 255))  # Gray
                            stone_images.append(placeholder)
                    else:
                        placeholder = Image.new('RGBA', (32, 32), (128, 128, 128, 255))
                        stone_images.append(placeholder)
                else:
                    # Empty stone placeholder
                    placeholder = Image.new('RGBA', (32, 32), (200, 200, 200, 255))  # Light gray
                    stone_images.append(placeholder)

            # Composite horizontally
            if stone_images:
                total_width = sum(img.width for img in stone_images)
                max_height = max(img.height for img in stone_images)
                composite = Image.new('RGBA', (total_width, max_height))
                x_offset = 0
                for img in stone_images:
                    composite.paste(img, (x_offset, 0))
                    x_offset += img.width

                # Save to BytesIO
                stones_io = BytesIO()
                composite.save(stones_io, format='PNG')
                stones_io.seek(0)
                stones_file = discord.File(stones_io, filename='stones.png')
                files.append(stones_file)

                # Set the composite stones image below the embed
                embed.set_image(url="attachment://stones.png")

            # ATK/HP in compact format
            embed.add_field(
                name="⚔️ Stats",
                value=f"ATK: **{record['atk_total']}** / HP: **{record['hp']}**",
                inline=True
            )

            # Bingo bonuses (only if they exist)
            valid_bingos = [b for b in record['bingo_bonuses'] if b and b != '—']
            if valid_bingos:
                bingo_text = ' | '.join(valid_bingos)
                embed.add_field(
                    name="🎯 Bingo Bonuses",
                    value=bingo_text[:100] + ("..." if len(bingo_text) > 100 else ""),
                    inline=False
                )

            # Video link as a clean button-style field
            embed.add_field(
                name="📺 Watch Run",
                value=f"[YouTube Link]({record['video_link']})",
                inline=False
            )

            # Footer with runner info
            embed.set_footer(text=f"Runner: {record['runner']} • Data from Pokemon Quest Speedrun Community")

            # Add a thumbnail (Pokémon icon)
            pokemon_thumbnails = {
                "Hitmonlee": "images/106.png",
                "Weepinbell": "images/070.png",
                "Machop": "images/066.png",
                "Victreebell": "images/071.png",
            }
            thumbnail_path = pokemon_thumbnails.get(record['pokemon'].strip(), "images/controller.png")
            embed.set_thumbnail(url=f"attachment://{thumbnail_path.split('/')[-1]}")
            # Add thumbnail file to attachments
            try:
                with open(thumbnail_path, 'rb') as f:
                    thumbnail_file = discord.File(f, filename=thumbnail_path.split('/')[-1])
                    files.append(thumbnail_file)
            except:
                pass

            await ctx.send(embed=embed, files=files)
        else:
            # Pagination setup
            total_pages = (len(unique_records) + 19) // 20
            page = 0

            # Pokémon emoji mapping
            pokemon_emojis = {
                "Hitmonlee": "👊", "Weepinbell": "🌿", "Machop": "💪",
                "Victreebell": "🍃", "Machamp": "💥", "": "❓"
            }

            # Build initial embed
            embed = discord.Embed(
                title=f"🎁 {ctx.author.display_name}'s Collection",
                description=f"You have claimed **{total_claims}** speedrun Pokémon!",
                color=discord.Color.gold()
            )

            start = page * 20
            end = min(start + 20, len(unique_records))
            collection_text = ""
            for i in range(start, end):
                record_hash = unique_records[i]
                record = dict(record_hash)
                emoji = pokemon_emojis.get(record['pokemon'].strip(), "🔹")
                count = record_counts[record_hash]
                count_str = f" (x{count})" if count > 1 else ""
                collection_text += f"{i+1}. {emoji} **{record['pokemon']}** {record['runner']} {record['time']}s {count_str}\n"

            embed.add_field(name="📜 Your Claims", value=collection_text[:1024], inline=False)

            embed.set_footer(text=f"Page {page+1}/{total_pages} | Use !collection <number> to view details! Use !dailypot to claim more Pokémon!")

            message = await ctx.send(embed=embed)
            view = CollectionView(unique_records, record_counts, pokemon_emojis, total_claims, ctx.author.display_name, total_pages, page, message)
            await message.edit(view=view)

    except Exception as e:
        await ctx.send(f"❌ Error: {e}")
        print(f"Error: {e}")

@bot.command(name='dailypot')
async def daily_pot(ctx):
    """Open the daily pot to claim a random speedrun Pokémon"""
    try:
        # Load claims data
        try:
            with open('daily_pot_claims.json', 'r') as f:
                claims = json.load(f)
        except FileNotFoundError:
            claims = {}

        user_id = str(ctx.author.id)
        now = datetime.now()
        today = str(date.today())

        # Check if user has used !dailypot within the last 16 hours
        if user_id in claims and claims[user_id].get("last_dailypot_use"):
            last_use_str = claims[user_id]["last_dailypot_use"]
            last_use = datetime.fromisoformat(last_use_str)
            if now - last_use < timedelta(hours=16):
                # On cooldown, display unclaimed Pokémon or message
                if "daily_pot" in claims and claims["daily_pot"].get("date") == today:
                    daily_pot = claims["daily_pot"]
                    selected_records = daily_pot["records"]
                    claimed = daily_pot["claimed"]
                    available_indices = [i for i in range(3) if str(i) not in claimed]
                    if available_indices:
                        available_records = [selected_records[i] for i in available_indices]
                        # Pokémon thumbnails
                        pokemon_thumbnails = {
                            "Hitmonlee": "images/106.png",
                            "Weepinbell": "images/070.png",
                            "Machop": "images/066.png",
                            "Victreebell": "images/071.png",
                        }

                        # Create composite thumbnail image for available Pokémon
                        thumbnail_images = []
                        for record in available_records:
                            thumb_path = pokemon_thumbnails.get(record['pokemon'].strip(), "images/controller.png")
                            try:
                                img = Image.open(thumb_path)
                                img = img.resize((64, 64))
                                thumbnail_images.append(img)
                            except:
                                placeholder = Image.new('RGBA', (64, 64), (128, 128, 128, 255))
                                thumbnail_images.append(placeholder)

                        # Composite horizontally with 10-pixel gaps
                        gap = 10
                        total_width = sum(img.width for img in thumbnail_images) + (len(thumbnail_images) - 1) * gap
                        max_height = max(img.height for img in thumbnail_images)
                        composite = Image.new('RGBA', (total_width, max_height))
                        x_offset = 0
                        for i, img in enumerate(thumbnail_images):
                            composite.paste(img, (x_offset, 0))
                            x_offset += img.width
                            if i < len(thumbnail_images) - 1:
                                x_offset += gap

                        # Save to BytesIO
                        thumbs_io = BytesIO()
                        composite.save(thumbs_io, format='PNG')
                        thumbs_io.seek(0)
                        thumbs_file = discord.File(thumbs_io, filename='pot_thumbs.png')

                        # Create embed
                        embed = discord.Embed(
                            title="🎁 Daily Pot (On Cooldown)",
                            description=f"Choose your speedrun Pokémon! Available options: {', '.join([str(i+1) for i in available_indices])}",
                            color=discord.Color.red()
                        )
                        embed.set_image(url="attachment://pot_thumbs.png")
                        embed.set_footer(text="You can only claim once every 2 minutes!")

                        # Create view with buttons for available indices
                        message = await ctx.send(embed=embed, file=thumbs_file)
                        view = DailyPotView(available_records, available_indices, ctx.author.id, message, ctx, is_cooldown=True)
                        await message.edit(view=view)

                        # Save updated claims (no change yet)
                        with open('daily_pot_claims.json', 'w') as f:
                            json.dump(claims, f, indent=4)
                    else:
                        await ctx.send("❌ Your daily pot is empty, check back tomorrow. All Pokémon have been claimed!")
                else:
                    await ctx.send("❌ Your daily pot is empty, check back tomorrow.")
                return

        # Update last_dailypot_use
        if user_id not in claims:
            claims[user_id] = {"last_claim": None, "collection": []}
        claims[user_id]["last_dailypot_use"] = now.isoformat()

        # Check if daily pot exists for today
        if "daily_pot" not in claims or claims["daily_pot"].get("date") != today:
            # Generate new daily pot
            unique_pokemon = list(set(r['pokemon'] for r in SPEEDRUN_DB if r['pokemon']))
            if len(unique_pokemon) < 3:
                await ctx.send("❌ Not enough Pokémon data available.")
                return

            selected_pokemon = random.sample(unique_pokemon, 3)
            selected_records = []
            for pokemon in selected_pokemon:
                pokemon_runs = [r for r in SPEEDRUN_DB if r['pokemon'] == pokemon]
                selected_records.append(random.choice(pokemon_runs))

            claims["daily_pot"] = {
                "date": today,
                "records": selected_records,
                "claimed": {}  # index: user_id
            }

        daily_pot = claims["daily_pot"]
        selected_records = daily_pot["records"]
        claimed = daily_pot["claimed"]

        # Get available indices (not claimed)
        available_indices = [i for i in range(3) if str(i) not in claimed]

        if not available_indices:
            if user_id == "205180213384970240":
                # Regenerate daily pot for dev
                unique_pokemon = list(set(r['pokemon'] for r in SPEEDRUN_DB if r['pokemon']))
                if len(unique_pokemon) < 3:
                    await ctx.send("❌ Not enough Pokémon data available.")
                    return

                selected_pokemon = random.sample(unique_pokemon, 3)
                selected_records = []
                for pokemon in selected_pokemon:
                    pokemon_runs = [r for r in SPEEDRUN_DB if r['pokemon'] == pokemon]
                    selected_records.append(random.choice(pokemon_runs))

                claims["daily_pot"] = {
                    "date": today,
                    "records": selected_records,
                    "claimed": {}  # index: user_id
                }

                # Reload daily_pot and claimed
                daily_pot = claims["daily_pot"]
                selected_records = daily_pot["records"]
                claimed = daily_pot["claimed"]
                available_indices = [i for i in range(3) if str(i) not in claimed]
            else:
                await ctx.send("❌ All Pokémon in today's pot have been claimed! Come back tomorrow.")
                return

        available_records = [selected_records[i] for i in available_indices]

        # Pokémon thumbnails
        pokemon_thumbnails = {
            "Hitmonlee": "images/106.png",
            "Weepinbell": "images/070.png",
            "Machop": "images/066.png",
            "Victreebell": "images/071.png",
        }

        # Create composite thumbnail image for available Pokémon
        thumbnail_images = []
        for record in available_records:
            thumb_path = pokemon_thumbnails.get(record['pokemon'].strip(), "images/controller.png")
            try:
                img = Image.open(thumb_path)
                img = img.resize((64, 64))
                thumbnail_images.append(img)
            except:
                placeholder = Image.new('RGBA', (64, 64), (128, 128, 128, 255))
                thumbnail_images.append(placeholder)

        # Composite horizontally with 10-pixel gaps
        gap = 10
        total_width = sum(img.width for img in thumbnail_images) + (len(thumbnail_images) - 1) * gap
        max_height = max(img.height for img in thumbnail_images)
        composite = Image.new('RGBA', (total_width, max_height))
        x_offset = 0
        for i, img in enumerate(thumbnail_images):
            composite.paste(img, (x_offset, 0))
            x_offset += img.width
            if i < len(thumbnail_images) - 1:
                x_offset += gap

        # Save to BytesIO
        thumbs_io = BytesIO()
        composite.save(thumbs_io, format='PNG')
        thumbs_io.seek(0)
        thumbs_file = discord.File(thumbs_io, filename='pot_thumbs.png')

        # Create embed
        embed = discord.Embed(
            title="🎁 Daily Pot",
            description=f"Choose your speedrun Pokémon! Available options: {', '.join([str(i+1) for i in available_indices])}",
            color=discord.Color.gold()
        )
        embed.set_image(url="attachment://pot_thumbs.png")
        embed.set_footer(text="You can only claim once every 2 minutes!")

        # Create view with buttons for available indices
        message = await ctx.send(embed=embed, file=thumbs_file)
        view = DailyPotView(available_records, available_indices, ctx.author.id, message, ctx)
        await message.edit(view=view)

        # Save updated claims
        with open('daily_pot_claims.json', 'w') as f:
            json.dump(claims, f, indent=4)

    except Exception as e:
        await ctx.send(f"❌ Error: {e}")
        print(f"Error: {e}")

class DailyPotView(discord.ui.View):
    def __init__(self, available_records, available_indices, priority_user_id, message, ctx, is_cooldown=False):
        super().__init__(timeout=300)  # 5 minutes timeout
        self.available_records = available_records
        self.available_indices = available_indices
        self.priority_user_id = priority_user_id
        self.priority_end_time = datetime.now() if is_cooldown else datetime.now() + timedelta(minutes=1)
        self.priority_attempts = 0
        self.message = message  # Reference to the message to edit footer
        self.ctx = ctx
        self.update_task = None

        # Dynamically add buttons for available options
        for i, idx in enumerate(available_indices):
            button = discord.ui.Button(
                label=str(idx + 1),
                style=discord.ButtonStyle.primary,
                emoji=f"{idx + 1}️⃣"
            )
            button.callback = self.create_callback(i)
            self.add_item(button)

        # Start footer update task if priority is active
        if self.priority_end_time > datetime.now():
            self.update_task = self.ctx.bot.loop.create_task(self.update_footer())

    async def update_footer(self):
        while datetime.now() < self.priority_end_time:
            remaining = self.priority_end_time - datetime.now()
            minutes = int(remaining.total_seconds() // 60)
            seconds = int(remaining.total_seconds() % 60)
            footer_text = f"Priority time remaining: {minutes}:{seconds:02d}"
            embed = self.message.embeds[0]
            embed.set_footer(text=footer_text)
            await self.message.edit(embed=embed)
            await asyncio.sleep(1)
        # After priority time, set back to normal footer
        embed = self.message.embeds[0]
        embed.set_footer(text="You can only claim once every 2 minutes!")
        await self.message.edit(embed=embed)

    def create_callback(self, button_index):
        async def callback(interaction: discord.Interaction):
            await self.handle_choice(interaction, button_index)
        return callback

    async def handle_choice(self, interaction: discord.Interaction, button_index: int):
        user_id_str = str(interaction.user.id)
        now = datetime.now()

        # Priority logic: Check if priority time is active
        if now < self.priority_end_time:
            if user_id_str != str(self.priority_user_id):
                self.priority_attempts += 1
                await interaction.response.send_message("⏰ Priority time! Only the user who opened the daily pot can claim for the next minute.", ephemeral=True)
                return
            # Priority user can claim without cooldown during priority time
        else:
            # Normal cooldown check after priority time
            try:
                with open('daily_pot_claims.json', 'r') as f:
                    claims = json.load(f)
            except FileNotFoundError:
                claims = {}

            # Check if user has claimed within the last 2 minutes
            if user_id_str in claims and claims[user_id_str].get("last_claim"):
                last_claim_str = claims[user_id_str]["last_claim"]
                last_claim = datetime.fromisoformat(last_claim_str)
                if now - last_claim < timedelta(minutes=2):
                    remaining_time = timedelta(minutes=2) - (now - last_claim)
                    minutes_left = int(remaining_time.total_seconds() // 60)
                    await interaction.response.send_message(f"❌ You've already claimed from the daily pot! Come back in {minutes_left} minutes.", ephemeral=True)
                    return

        actual_index = self.available_indices[button_index]
        record = self.available_records[button_index]

        # Claim the Pokémon
        if user_id_str not in claims:
            claims[user_id_str] = {"last_claim": None, "collection": []}

        claims[user_id_str]["last_claim"] = now.isoformat()
        claims[user_id_str]["collection"].append(record)

        # Mark as claimed in daily_pot
        claims["daily_pot"]["claimed"][str(actual_index)] = user_id_str

        with open('daily_pot_claims.json', 'w') as f:
            json.dump(claims, f, indent=4)

        # Disable the clicked button
        self.children[button_index].disabled = True
        await interaction.response.edit_message(view=self)

        # Send the full record embed
        await self.send_record_embed(interaction, record, self.priority_user_id, self.priority_attempts)

    async def send_record_embed(self, interaction, record, priority_user_id=None, priority_attempts=0):
        # Status indicator
        status_emoji = "🏆" if record['status'] == 'WR' else "🔥" if record['status'] == 'PB' else "📜"

        # Pokémon emoji mapping
        pokemon_emojis = {
            "Hitmonlee": "👊", "Weepinbell": "🌿", "Machop": "💪",
            "Victreebell": "🍃", "Machamp": "💥", "": "❓"
        }
        pokemon_emoji = pokemon_emojis.get(record['pokemon'].strip(), "🔹")

        # Category colors
        category_colors = {
            "12-Boss": discord.Color.blue(),
            "12B-no-buffer": discord.Color.red(),
            "12B-solo": discord.Color.green(),
            "Any%": discord.Color.gold(),
            "Any%-DLC": discord.Color.purple()
        }

        embed = discord.Embed(
            title=f"{pokemon_emoji} {record['runner']}'s {record['pokemon']}",
            description=f"**{record['category']}** • Time: `{record['time']}`s • **IV:** {record['overall_iv']} • **Status:** {status_emoji} {record['status']}",
            color=category_colors.get(record['category'], discord.Color.default())
        )

        # Create composite stone image
        files = []
        stone_images = []
        for s in record['move_stones']:
            if s:
                file_path = STONE_FILES.get(s)
                if file_path:
                    try:
                        img = Image.open(file_path)
                        img = img.resize((32, 32))
                        stone_images.append(img)
                    except:
                        placeholder = Image.new('RGBA', (32, 32), (128, 128, 128, 255))
                        stone_images.append(placeholder)
                else:
                    placeholder = Image.new('RGBA', (32, 32), (128, 128, 128, 255))
                    stone_images.append(placeholder)
            else:
                placeholder = Image.new('RGBA', (32, 32), (200, 200, 200, 255))
                stone_images.append(placeholder)

        # Composite horizontally
        if stone_images:
            total_width = sum(img.width for img in stone_images)
            max_height = max(img.height for img in stone_images)
            composite = Image.new('RGBA', (total_width, max_height))
            x_offset = 0
            for img in stone_images:
                composite.paste(img, (x_offset, 0))
                x_offset += img.width

            stones_io = BytesIO()
            composite.save(stones_io, format='PNG')
            stones_io.seek(0)
            stones_file = discord.File(stones_io, filename='stones.png')
            files.append(stones_file)

            embed.set_image(url="attachment://stones.png")

        # Stats
        embed.add_field(name="⚔️ Stats", value=f"ATK: **{record['atk_total']}** / HP: **{record['hp']}**", inline=True)

        # Bingo bonuses
        valid_bingos = [b for b in record['bingo_bonuses'] if b and b != '—']
        if valid_bingos:
            bingo_text = ' | '.join(valid_bingos)
            embed.add_field(name="🎯 Bingo Bonuses", value=bingo_text[:100] + ("..." if len(bingo_text) > 100 else ""), inline=False)

        # Video link
        embed.add_field(name="📺 Watch Run", value=f"[YouTube Link]({record['video_link']})", inline=False)

        # Footer
        embed.set_footer(text=f"Runner: {record['runner']} • Data from Pokemon Quest Speedrun Community")

        # Thumbnail
        pokemon_thumbnails = {
            "Hitmonlee": "images/106.png",
            "Weepinbell": "images/070.png",
            "Machop": "images/066.png",
            "Victreebell": "images/071.png",
        }
        thumbnail_path = pokemon_thumbnails.get(record['pokemon'].strip(), "images/controller.png")
        embed.set_thumbnail(url=f"attachment://{thumbnail_path.split('/')[-1]}")
        try:
            with open(thumbnail_path, 'rb') as f:
                thumbnail_file = discord.File(f, filename=thumbnail_path.split('/')[-1])
                files.append(thumbnail_file)
        except:
            pass

        await interaction.followup.send(embed=embed, files=files)

@bot.command(name='devpot')
async def dev_pot(ctx):
    """Dev-only command: Open the daily pot without restrictions, allowing regeneration and unlimited claims"""
    user_id = str(ctx.author.id)

    # Restrict to dev user
    if user_id != "205180213384970240":
        await ctx.send("❌ This command is restricted to developers only.")
        return

    try:
        # Load claims data
        try:
            with open('daily_pot_claims.json', 'r') as f:
                claims = json.load(f)
        except FileNotFoundError:
            claims = {}

        now = datetime.now()
        today = str(date.today())

        # Always regenerate daily pot for dev
        unique_pokemon = list(set(r['pokemon'] for r in SPEEDRUN_DB if r['pokemon']))
        if len(unique_pokemon) < 3:
            await ctx.send("❌ Not enough Pokémon data available.")
            return

        selected_pokemon = random.sample(unique_pokemon, 3)
        selected_records = []
        for pokemon in selected_pokemon:
            pokemon_runs = [r for r in SPEEDRUN_DB if r['pokemon'] == pokemon]
            selected_records.append(random.choice(pokemon_runs))

        claims["daily_pot"] = {
            "date": today,
            "records": selected_records,
            "claimed": {}  # Reset claimed for dev
        }

        daily_pot = claims["daily_pot"]
        selected_records = daily_pot["records"]
        claimed = daily_pot["claimed"]

        # Get available indices (all since we reset)
        available_indices = [i for i in range(3) if str(i) not in claimed]
        available_records = [selected_records[i] for i in available_indices]

        # Pokémon thumbnails
        pokemon_thumbnails = {
            "Hitmonlee": "images/106.png",
            "Weepinbell": "images/070.png",
            "Machop": "images/066.png",
            "Victreebell": "images/071.png",
        }

        # Create composite thumbnail image for available Pokémon
        thumbnail_images = []
        for record in available_records:
            thumb_path = pokemon_thumbnails.get(record['pokemon'].strip(), "images/controller.png")
            try:
                img = Image.open(thumb_path)
                img = img.resize((64, 64))
                thumbnail_images.append(img)
            except:
                placeholder = Image.new('RGBA', (64, 64), (128, 128, 128, 255))
                thumbnail_images.append(placeholder)

        # Composite horizontally with 10-pixel gaps
        gap = 10
        total_width = sum(img.width for img in thumbnail_images) + (len(thumbnail_images) - 1) * gap
        max_height = max(img.height for img in thumbnail_images)
        composite = Image.new('RGBA', (total_width, max_height))
        x_offset = 0
        for i, img in enumerate(thumbnail_images):
            composite.paste(img, (x_offset, 0))
            x_offset += img.width
            if i < len(thumbnail_images) - 1:
                x_offset += gap

        # Save to BytesIO
        thumbs_io = BytesIO()
        composite.save(thumbs_io, format='PNG')
        thumbs_io.seek(0)
        thumbs_file = discord.File(thumbs_io, filename='pot_thumbs.png')

        # Create embed
        embed = discord.Embed(
            title="🎁 Dev Pot",
            description=f"Choose your speedrun Pokémon! Available options: {', '.join([str(i+1) for i in available_indices])}",
            color=discord.Color.red()
        )
        embed.set_image(url="attachment://pot_thumbs.png")
        embed.set_footer(text="Dev command: No cooldowns or restrictions!")

        # Create view with buttons for available indices
        view = DevPotView(available_records, available_indices, ctx.author.id)

        # Save updated claims
        with open('daily_pot_claims.json', 'w') as f:
            json.dump(claims, f, indent=4)

        await ctx.send(embed=embed, file=thumbs_file, view=view)

    except Exception as e:
        await ctx.send(f"❌ Error: {e}")
        print(f"Error: {e}")
    except Exception as e:
        await ctx.send(f"❌ Error: {e}")


class DevPotView(discord.ui.View):
    def __init__(self, available_records, available_indices, user_id):
        super().__init__(timeout=300)  # 5 minutes timeout
        self.available_records = available_records
        self.available_indices = available_indices
        self.user_id = user_id

        # Dynamically add buttons for available options
        for i, idx in enumerate(available_indices):
            button = discord.ui.Button(
                label=str(idx + 1),
                style=discord.ButtonStyle.primary,
                emoji=f"{idx + 1}️⃣"
            )
            button.callback = self.create_callback(i)
            self.add_item(button)

    def create_callback(self, button_index):
        async def callback(interaction: discord.Interaction):
            await self.handle_choice(interaction, button_index)
        return callback

    async def handle_choice(self, interaction: discord.Interaction, button_index: int):
        user_id_str = str(interaction.user.id)

        # Restrict to dev user
        if user_id_str != "205180213384970240":
            await interaction.response.send_message("❌ This action is restricted to developers only.", ephemeral=True)
            return

        actual_index = self.available_indices[button_index]
        record = self.available_records[button_index]

        # Load claims to update
        try:
            with open('daily_pot_claims.json', 'r') as f:
                claims = json.load(f)
        except FileNotFoundError:
            claims = {}

        # Claim the Pokémon (no cooldown for dev)
        if user_id_str not in claims:
            claims[user_id_str] = {"last_claim": None, "collection": []}

        # Dev can claim multiple times, add to collection
        claims[user_id_str]["collection"].append(record)

        # Mark as claimed in daily_pot
        claims["daily_pot"]["claimed"][str(actual_index)] = user_id_str

        with open('daily_pot_claims.json', 'w') as f:
            json.dump(claims, f, indent=4)

        # Disable the clicked button
        self.children[button_index].disabled = True
        await interaction.response.edit_message(view=self)

        # Send the full record embed
        await self.send_record_embed(interaction, record)

    async def send_record_embed(self, interaction, record):
        # Status indicator
        status_emoji = "🏆" if record['status'] == 'WR' else "🔥" if record['status'] == 'PB' else "📜"

        # Pokémon emoji mapping
        pokemon_emojis = {
            "Hitmonlee": "👊", "Weepinbell": "🌿", "Machop": "💪",
            "Victreebell": "🍃", "Machamp": "💥", "": "❓"
        }
        pokemon_emoji = pokemon_emojis.get(record['pokemon'].strip(), "🔹")

        # Category colors
        category_colors = {
            "12-Boss": discord.Color.blue(),
            "12B-no-buffer": discord.Color.red(),
            "12B-solo": discord.Color.green(),
            "Any%": discord.Color.gold(),
            "Any%-DLC": discord.Color.purple()
        }

        embed = discord.Embed(
            title=f"{pokemon_emoji} {record['runner']}'s {record['pokemon']}",
            description=f"**{record['category']}** • Time: `{record['time']}`s • **IV:** {record['overall_iv']} • **Status:** {status_emoji} {record['status']}",
            color=category_colors.get(record['category'], discord.Color.default())
        )

        # Create composite stone image
        files = []
        stone_images = []
        for s in record['move_stones']:
            if s:
                file_path = STONE_FILES.get(s)
                if file_path:
                    try:
                        img = Image.open(file_path)
                        img = img.resize((32, 32))
                        stone_images.append(img)
                    except:
                        placeholder = Image.new('RGBA', (32, 32), (128, 128, 128, 255))
                        stone_images.append(placeholder)
                else:
                    placeholder = Image.new('RGBA', (32, 32), (128, 128, 128, 255))
                    stone_images.append(placeholder)
            else:
                placeholder = Image.new('RGBA', (32, 32), (200, 200, 200, 255))
                stone_images.append(placeholder)

        # Composite horizontally
        if stone_images:
            total_width = sum(img.width for img in stone_images)
            max_height = max(img.height for img in stone_images)
            composite = Image.new('RGBA', (total_width, max_height))
            x_offset = 0
            for img in stone_images:
                composite.paste(img, (x_offset, 0))
                x_offset += img.width

            stones_io = BytesIO()
            composite.save(stones_io, format='PNG')
            stones_io.seek(0)
            stones_file = discord.File(stones_io, filename='stones.png')
            files.append(stones_file)

            embed.set_image(url="attachment://stones.png")

        # Stats
        embed.add_field(name="⚔️ Stats", value=f"ATK: **{record['atk_total']}** / HP: **{record['hp']}**", inline=True)

        # Bingo bonuses
        valid_bingos = [b for b in record['bingo_bonuses'] if b and b != '—']
        if valid_bingos:
            bingo_text = ' | '.join(valid_bingos)
            embed.add_field(name="🎯 Bingo Bonuses", value=bingo_text[:100] + ("..." if len(bingo_text) > 100 else ""), inline=False)

        # Video link
        embed.add_field(name="📺 Watch Run", value=f"[YouTube Link]({record['video_link']})", inline=False)

        # Footer
        embed.set_footer(text=f"Runner: {record['runner']} • Data from Pokemon Quest Speedrun Community")

        # Thumbnail
        pokemon_thumbnails = {
            "Hitmonlee": "images/106.png",
            "Weepinbell": "images/070.png",
            "Machop": "images/066.png",
            "Victreebell": "images/071.png",
        }
        thumbnail_path = pokemon_thumbnails.get(record['pokemon'].strip(), "images/controller.png")
        embed.set_thumbnail(url=f"attachment://{thumbnail_path.split('/')[-1]}")
        try:
            with open(thumbnail_path, 'rb') as f:
                thumbnail_file = discord.File(f, filename=thumbnail_path.split('/')[-1])
                files.append(thumbnail_file)
        except:
            pass

        await interaction.followup.send(embed=embed, files=files)



class CollectionView(discord.ui.View):
    def __init__(self, unique_records, record_counts, pokemon_emojis, total_claims, author_display_name, total_pages, current_page, message):
        super().__init__(timeout=300)  # 5 minutes timeout
        self.unique_records = unique_records
        self.record_counts = record_counts
        self.pokemon_emojis = pokemon_emojis
        self.total_claims = total_claims
        self.author_display_name = author_display_name
        self.total_pages = total_pages
        self.current_page = current_page
        self.message = message

        # Add Previous button
        prev_button = discord.ui.Button(label="Previous", style=discord.ButtonStyle.secondary, emoji="⬅️")
        prev_button.callback = self.previous_page
        prev_button.disabled = self.current_page == 0
        self.add_item(prev_button)

        # Add Next button
        next_button = discord.ui.Button(label="Next", style=discord.ButtonStyle.secondary, emoji="➡️")
        next_button.callback = self.next_page
        next_button.disabled = self.current_page >= self.total_pages - 1
        self.add_item(next_button)

    async def update_embed(self):
        embed = discord.Embed(
            title=f"🎁 {self.author_display_name}'s Collection",
            description=f"You have claimed **{self.total_claims}** speedrun Pokémon!",
            color=discord.Color.gold()
        )

        start = self.current_page * 20
        end = min(start + 20, len(self.unique_records))
        collection_text = ""
        for i in range(start, end):
            record_hash = self.unique_records[i]
            record = dict(record_hash)
            emoji = self.pokemon_emojis.get(record['pokemon'].strip(), "🔹")
            count = self.record_counts[record_hash]
            count_str = f" (x{count})" if count > 1 else ""
            collection_text += f"{i+1}. {emoji} **{record['pokemon']}** {record['runner']} {record['time']}s {count_str}\n"

        embed.add_field(name="📜 Your Claims", value=collection_text[:1024], inline=False)

        embed.set_footer(text=f"Page {self.current_page+1}/{self.total_pages} | Use !collection <number> to view details! Use !dailypot to claim more Pokémon!")

        await self.message.edit(embed=embed, view=self)

    async def previous_page(self, interaction: discord.Interaction):
        if self.current_page > 0:
            self.current_page -= 1
            self.children[0].disabled = self.current_page == 0  # Disable Previous if on first page
            self.children[1].disabled = False  # Enable Next
            await self.update_embed()
        await interaction.response.defer()

    async def next_page(self, interaction: discord.Interaction):
        if self.current_page < self.total_pages - 1:
            self.current_page += 1
            self.children[1].disabled = self.current_page >= self.total_pages - 1  # Disable Next if on last page
            self.children[0].disabled = False  # Enable Previous
            await self.update_embed()
        await interaction.response.defer()

# Run bot
TOKEN = os.getenv('DISCORD_BOT_TOKEN')
if not TOKEN:
    raise RuntimeError(
        "DISCORD_BOT_TOKEN is not set. Create a .env file (see .env.example) "
        "or export the variable before running the bot."
    )
bot.run(TOKEN)
