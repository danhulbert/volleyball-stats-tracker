import streamlit as st
import pandas as pd
import numpy as np
from voice_recognition import voice_recognition_component
import database as db
import os

# Set page configuration
st.set_page_config(
    page_title="Voice-Controlled Volleyball Stats Tracker",
    page_icon="🏐",
    layout="wide"
)

# Define volleyball skills (static column headers)
VOLLEYBALL_SKILLS = [
    "Serve Attempt", "Serve Ace", "Serve Error", 
    "Pass Zero", "Pass One", "Pass Two", "Pass Three", 
    "Spike Attempt", "Kill", "Spike Error", 
    "Block", "Assist", "Ball handling Error"
]

# Initialize session state for stats table if not already present
if 'stats_df' not in st.session_state:
    st.session_state.stats_df = None
    
if 'players' not in st.session_state:
    st.session_state.players = []
    
if 'listening' not in st.session_state:
    st.session_state.listening = False
    
if 'last_command' not in st.session_state:
    st.session_state.last_command = ""
    
if 'command_history' not in st.session_state:
    st.session_state.command_history = []
    
if 'current_team_id' not in st.session_state:
    st.session_state.current_team_id = None

def create_stats_dataframe(players):
    """Create a stats dataframe with players as rows and skills as columns."""
    # Create a dataframe with players as index and skills as columns
    data = {}
    for skill in VOLLEYBALL_SKILLS:
        data[skill] = [0] * len(players)
    
    df = pd.DataFrame(data, index=players)
    return df

def handle_voice_command(command):
    """Process a voice command and update the stats sheet."""
    if not command or not isinstance(command, str):
        return
    
    # Store the last command
    st.session_state.last_command = command
    
    # Add command to history (limit to 10 most recent)
    st.session_state.command_history.insert(0, command)
    st.session_state.command_history = st.session_state.command_history[:10]
    
    # Split the command into words
    words = command.strip().lower().split()
    
    # Need at least two words for player and skill
    if len(words) < 2:
        return
    
    # Try to match player name (could be multiple words)
    player_name = None
    for player in st.session_state.players:
        player_lower = player.lower()
        if player_lower in command.lower():
            player_name = player
            break
    
    if not player_name:
        return
    
    # Try to match skill
    skill = None
    for volleyball_skill in VOLLEYBALL_SKILLS:
        if volleyball_skill.lower() in command.lower():
            skill = volleyball_skill
            break
    
    if not skill:
        return
    
    # Update the stats dataframe
    if player_name in st.session_state.stats_df.index and skill in st.session_state.stats_df.columns:
        # Update local dataframe
        st.session_state.stats_df.loc[player_name, skill] += 1
        
        # Update database if we have a team ID
        if st.session_state.current_team_id:
            try:
                # Get player from database by name
                player = db.get_player_by_name(player_name)
                if player:
                    # Update the stat in database
                    db.update_player_stat(player.id, skill)
            except Exception as e:
                # If database update fails, just show a warning but don't interrupt the app
                st.warning(f"Could not save stat to database: {str(e)}", icon="⚠️")
            
        # Force rerun to update the display
        st.rerun()

def load_existing_team():
    """Check if there's a recent team in the database and prompt to load it"""
    try:
        recent_team = db.get_most_recent_team()
        if recent_team:
            team_id = recent_team.id
            team_name = recent_team.name
            team, players = db.get_team_with_players(team_id)
            player_names = [p.name for p in players]
            
            st.warning(f"Found existing team: {team_name}")
            
            # Load button in the warning
            col1, col2 = st.columns([1, 2])
            with col1:
                load_team = st.button("Load Team", key="load_existing")
            with col2:
                st.write("or enter new team details below.")
                
            if load_team:
                st.session_state.current_team_id = team_id
                st.session_state.players = player_names
                
                # Load stats from database
                st.session_state.stats_df = db.get_all_stats_for_team(team_id)
                
                # Check if any columns are missing and add them
                for skill in VOLLEYBALL_SKILLS:
                    if skill not in st.session_state.stats_df.columns:
                        st.session_state.stats_df[skill] = 0
                
                st.success(f"Loaded team: {team_name}")
                st.rerun()
        return False
    except Exception as e:
        st.error(f"Database connection error. Please create a new team. Error details: {str(e)}")
        return False

# Main app layout
st.title("🏐 Voice-Controlled Volleyball Stats Tracker")

# Player setup section (only if stats_df is not initialized)
if st.session_state.stats_df is None:
    st.header("Team Setup")
    
    # Check for existing teams in database
    load_existing_team()
    
    with st.form("player_setup_form"):
        # Team name input
        team_name = st.text_input("Team Name", value="My Volleyball Team")
        
        st.write("Enter player names (one per line):")
        players_input = st.text_area("", height=200)
        submitted = st.form_submit_button("Start Tracking")
        
        if submitted:
            players = [p.strip() for p in players_input.split('\n') if p.strip()]
            if not players:
                st.error("Please enter at least one player name.")
            else:
                try:
                    # Create a team in the database
                    team_id = db.create_team(team_name)
                    
                    # Add players to the team
                    db.add_players_to_team(team_id, players)
                    
                    # Initialize stats for each player
                    for player_name in players:
                        player = db.get_player_by_name(player_name)
                        if player:
                            db.initialize_player_stats(player.id, VOLLEYBALL_SKILLS)
                    
                    # Store current team ID in session state
                    st.session_state.current_team_id = team_id
                    st.session_state.players = players
                    st.session_state.stats_df = create_stats_dataframe(players)
                    
                    # Save initial stats to database
                    db.save_current_stats(team_id, st.session_state.stats_df)
                    
                    st.success("Team created successfully!")
                    st.rerun()
                except Exception as e:
                    # If database operations fail, we'll still create the team in memory
                    st.warning(f"Database connection issue: {str(e)}")
                    st.info("Creating team in memory only (stats won't be saved permanently)")
                    
                    # Just use in-memory stats
                    st.session_state.current_team_id = None
                    st.session_state.players = players
                    st.session_state.stats_df = create_stats_dataframe(players)
                    st.rerun()
else:
    # Stats tracking section
    col1, col2 = st.columns([3, 1])
    
    with col1:
        st.header("Stats Sheet")
        
        # Display stats table with highlighted column headers
        st.dataframe(
            st.session_state.stats_df,
            use_container_width=True,
            height=400
        )
        
        # Add button row
        btn_col1, btn_col2, btn_col3 = st.columns(3)
        
        # Add a button to save stats
        with btn_col1:
            if st.button("Save Stats"):
                if st.session_state.current_team_id:
                    try:
                        db.save_current_stats(st.session_state.current_team_id, st.session_state.stats_df)
                        st.success("Stats saved to database successfully!")
                    except Exception as e:
                        st.error(f"Failed to save stats: {str(e)}")
                else:
                    st.warning("Cannot save stats - team not stored in database")
        
        # Add a button to reset stats
        with btn_col2:
            if st.button("Reset Stats"):
                # Always reset the dataframe in memory
                st.session_state.stats_df = create_stats_dataframe(st.session_state.players)
                
                # Try to save to database if we have a team ID
                if st.session_state.current_team_id:
                    try:
                        db.save_current_stats(st.session_state.current_team_id, st.session_state.stats_df)
                        st.success("Stats reset and saved to database!")
                    except Exception as e:
                        st.warning(f"Stats reset in memory but database update failed: {str(e)}")
                else:
                    st.success("Stats reset in memory only!")
                
                st.rerun()
        
        # Add a button to start over with new players
        with btn_col3:
            if st.button("Start Over (New Team)"):
                st.session_state.stats_df = None
                st.session_state.players = []
                st.session_state.listening = False
                st.session_state.current_team_id = None
                st.rerun()
    
    with col2:
        st.header("Input Controls")
        
        # Create tabs for voice and manual input
        voice_tab, manual_tab = st.tabs(["Voice Input", "Manual Input"])
        
        with voice_tab:
            # Toggle for voice recognition
            listening = st.toggle("Enable Voice Recognition", value=st.session_state.listening)
            
            if listening != st.session_state.listening:
                st.session_state.listening = listening
                st.rerun()
            
            if st.session_state.listening:
                st.markdown("### Say the player name and skill")
                st.markdown("Example: *'John Serve Ace'* or *'Emily Kill'*")
                
                # Display the voice recognition component
                command = voice_recognition_component(key="voice_recognition")
                if command:
                    handle_voice_command(command)
                
                # Show last recognized command
                st.markdown("### Last Command")
                st.write(st.session_state.last_command or "No command detected yet")
                
                # Command history
                st.markdown("### Command History")
                for cmd in st.session_state.command_history:
                    st.write(f"- {cmd}")
            else:
                st.info("Enable voice recognition to start tracking stats with voice commands.")
        
        with manual_tab:
            st.markdown("### Add Stats Manually")
            
            # Add a subheading and explanation
            st.write("Option 1: Select from dropdowns")
            
            # Add dropdown selections for player and skill
            player_name = st.selectbox("Select Player", st.session_state.players)
            skill = st.selectbox("Select Skill", VOLLEYBALL_SKILLS)
            
            # Button to manually add a stat
            if st.button("Add Stat from Dropdowns"):
                if player_name and skill:
                    # Create manual command
                    manual_command = f"{player_name} {skill}"
                    handle_voice_command(manual_command)
                    st.success(f"Added: {manual_command}")
            
            # Add a divider
            st.markdown("---")
            
            # Second option - text input
            st.write("Option 2: Enter command as text")
            st.write("Format: '[Player Name] [Skill]'")
            
            # Text input for command
            text_command = st.text_input("Enter command", placeholder="e.g. John Serve Ace")
            
            # Button to add stat from text
            if st.button("Add Stat from Text"):
                if text_command:
                    handle_voice_command(text_command)
                    st.success(f"Added: {text_command}")
        
        # Display available skills for reference
        with st.expander("Available Skills Reference"):
            for skill in VOLLEYBALL_SKILLS:
                st.write(f"- {skill}")
                
        # Display available players for reference
        with st.expander("Player List"):
            for player in st.session_state.players:
                st.write(f"- {player}")
