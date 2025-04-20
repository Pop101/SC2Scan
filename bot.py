import discord
from discord import app_commands
from discord.ext import tasks
from pytz import timezone
from modules.parse_facts import parse_player_facts
from modules.config import config as global_config
import datetime
import os
import json
import re
from collections import defaultdict
import traceback
import warnings

# Set timezone
tz = timezone('US/Pacific')

# Create bot with slash command functionality
class BotClient(discord.Client):
    def __init__(self):
        intents = discord.Intents.default()
        intents.message_content = True
        super().__init__(intents=intents)
        
        # Set up command tree for slash commands
        self.tree = app_commands.CommandTree(self)
        
        # Create config directory if it doesn't exist
        if not os.path.exists('server_configs'):
            os.makedirs('server_configs')

        self.setup_commands()
    
    def setup_commands(self):
        """Set up the slash commands"""
        
        # Define set_weekly command
        @self.tree.command(name="set_weekly", description="Set the current channel for weekly announcements")
        async def set_weekly_channel(interaction: discord.Interaction):
            # Check if user has manage channels permission
            if not interaction.user.guild_permissions.manage_channels:
                await interaction.response.send_message("You need 'Manage Channels' permission to use this command.", ephemeral=True)
                return
            
            guild_id = str(interaction.guild_id)
            channel_id = interaction.channel_id
            
            config = self.load_server_config(guild_id)
            config['weekly_channel'] = channel_id
            self.save_server_config(guild_id, config)
            
            await interaction.response.send_message(f'Weekly announcement channel set to {interaction.channel.mention}', ephemeral=True)
        
        # Define set_scan command
        @self.tree.command(name="set_scan", description="Set the current channel to scan for BattleNet accounts")
        async def set_scan_channel(interaction: discord.Interaction):
            # Check if user has manage channels permission
            if not interaction.user.guild_permissions.manage_channels:
                await interaction.response.send_message("You need 'Manage Channels' permission to use this command.", ephemeral=True)
                return
            
            guild_id = str(interaction.guild_id)
            channel_id = interaction.channel_id
            
            config = self.load_server_config(guild_id)
            config['scan_channel'] = channel_id
            self.save_server_config(guild_id, config)
            
            await interaction.response.send_message(f'BattleNet account scanning channel set to {interaction.channel.mention}', ephemeral=True)
    
    async def setup_hook(self):
        # Start background tasks
        self.post_weekly.start()
        self.find_accounts.start()
        
        # Register slash commands with Discord
        await self.tree.sync()
    
    async def on_ready(self):
        print(f'Logged in as {self.user.name} ({self.user.id})')
        print(f'Invite link: https://discord.com/api/oauth2/authorize?client_id={self.user.id}&permissions=2048&scope=bot%20applications.commands')
        print('------')
    
    def load_server_config(self, guild_id):
        """Load server config from file"""
        config_path = os.path.join('server_configs', f'{guild_id}.json')
        
        if not os.path.exists(config_path):
            return {
                'weekly_channel': None,
                'scan_channel': None, 
                'last_weekly_post': datetime.datetime.min.replace(tzinfo=tz).isoformat(),
                'bnet_accounts': {}
                }
        
        with open(config_path, 'r') as f:
            return json.load(f)
    
    def save_server_config(self, guild_id, config):
        """Save server config to file"""
        config_path = os.path.join('server_configs', f'{guild_id}.json')
        
        with open(config_path, 'w') as f:
            json.dump(config, f, indent=4)
    
    def iter_servers(self):
        """Iterate through all server configs"""
        for filename in os.listdir('server_configs'):
            if filename.endswith('.json'):
                guild_id = filename[:-5]  # Remove .json extension
                config = self.load_server_config(guild_id)
                yield guild_id, config
    
    @tasks.loop(hours=global_config['hours_between_scans'])
    async def find_accounts(self):
        """Scan channels for BattleNet accounts"""
        print("Finding BattleNet accounts...")
        
        # Iterate through all servers
        for guild_id, config in self.iter_servers():
            if not config.get('scan_channel'):
                continue
            
            guild = self.get_guild(int(guild_id))
            if not guild:
                continue
                
            channel = guild.get_channel(config['scan_channel'])
            if not channel:
                continue
            
            print(f"Scanning messages in {guild.name}...")
            accounts_found = 0
            async for message in channel.history(limit=global_config['max_messages_scanned'], oldest_first=True):
                # Check if message contains a BattleNet account
                bnet_account = re.search(r'\w+\s*#\d{1,9}', message.content)
                if bnet_account:
                    # Add account to config
                    account_name = re.sub(r'\s', '', bnet_account.group(0))
                    config['bnet_accounts'][account_name] = message.author.id
                    self.save_server_config(guild_id, config)
                    print(f"\tFound BattleNet account: {account_name}")
                    accounts_found += 1
            print(f"Found {accounts_found} BattleNet accounts in {guild.name}")
            
    @tasks.loop(hours=global_config['hours_between_scans'])
    async def post_weekly(self):
        """Post weekly announcement"""        
        for guild_id, config in self.iter_servers():
            if not config.get('weekly_channel'):
                continue
            
            guild = self.get_guild(int(guild_id))
            if not guild:
                continue
                
            channel = guild.get_channel(config['weekly_channel'])
            if not channel:
                continue
            
            # Check if it's time to post the weekly announcement
            last_post = datetime.datetime.fromisoformat(config['last_weekly_post'])
            if datetime.datetime.now(tz) - last_post < datetime.timedelta(days=7):
                continue
            
            print(f"Posting weekly announcement in {guild.name}...")

            # Get ALL player stats
            player_stats = list()
            for account_name, _ in config['bnet_accounts'].items():
                try:
                    print(f"\tGetting player stats for {account_name}...")
                    player_stats.extend(list(parse_player_facts(account_name, cutoff_date=last_post)))
                except Exception as e:
                    print(f"Error getting player stats for {account_name}: {e}")
                    traceback.print_exc()
                    print("\n")
            
            print('Player stats:')
            for fact in sorted(player_stats, key=lambda fact: fact.impressive(), reverse=True):
                print("\t", fact.player_name, fact, fact.impressive())
                
            # Remove low-interest facts & sort
            player_stats = [fact for fact in player_stats if fact.impressive() > 5]

            # Select facts with dynamic penalty for player diversity
            selected_facts = []
            player_penalties = defaultdict(lambda: 1.0)
            while player_stats:
                player_stats.sort(key=lambda fact: fact.impressive() * player_penalties[fact.player_id], reverse=True)
                
                top_fact = player_stats.pop(0)
                selected_facts.append(top_fact)
                
                player_penalties[top_fact.player_id] *= 0.8
            
            # No facts - Skip this week
            print(f"Found a total of {len(selected_facts)} facts")
            if not selected_facts:
                continue
            
            # Compose message of top 6 facts
            message = f"Weekly stats for {datetime.datetime.now().strftime('%B %d, %Y')}:\n"
            for i, fact in enumerate(selected_facts[:min(6, len(selected_facts))], start=1):
                mention = fact.player_name
                if fact.battle_tag in config['bnet_accounts']:
                    mention += f" <@{config['bnet_accounts'][fact.battle_tag]}>"
                else:
                    warnings.warn(f"Warning: BattleTag {fact.battle_tag} not found in scanned channels")
                message += f"{i}. {mention} {fact}\n"
            
            await channel.send(message)
            config['last_weekly_post'] = datetime.datetime.now(tz).isoformat()
            self.save_server_config(guild_id, config)
    
    # Wait until bot is ready before starting tasks
    @find_accounts.before_loop
    @post_weekly.before_loop
    async def before_tasks(self):
        await self.wait_until_ready()

# Create and run bot
client = BotClient()
client.run(global_config['token'])