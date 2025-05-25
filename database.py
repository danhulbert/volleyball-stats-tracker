import os
import pandas as pd
from sqlalchemy import create_engine, Column, Integer, String, ForeignKey, DateTime, update
from sqlalchemy.ext.declarative import declarative_base
from sqlalchemy.orm import sessionmaker, relationship
from datetime import datetime

# Get database URL from environment variable
DATABASE_URL = os.environ.get('DATABASE_URL', '')

# Create SQLAlchemy engine and session
engine = create_engine(DATABASE_URL)
Session = sessionmaker(bind=engine)
Base = declarative_base()

# Define database models
class Team(Base):
    __tablename__ = 'teams'
    
    id = Column(Integer, primary_key=True)
    name = Column(String, nullable=False)
    created_at = Column(DateTime, default=datetime.now)
    
    # Relationships
    players = relationship("Player", back_populates="team", cascade="all, delete-orphan")
    
    def __repr__(self):
        return f"<Team(name='{self.name}')>"

class Player(Base):
    __tablename__ = 'players'
    
    id = Column(Integer, primary_key=True)
    name = Column(String, nullable=False)
    team_id = Column(Integer, ForeignKey('teams.id'))
    created_at = Column(DateTime, default=datetime.now)
    
    # Relationships
    team = relationship("Team", back_populates="players")
    stats = relationship("Stat", back_populates="player", cascade="all, delete-orphan")
    
    def __repr__(self):
        return f"<Player(name='{self.name}')>"

class Stat(Base):
    __tablename__ = 'stats'
    
    id = Column(Integer, primary_key=True)
    player_id = Column(Integer, ForeignKey('players.id'))
    skill_name = Column(String, nullable=False)
    count = Column(Integer, default=0)
    created_at = Column(DateTime, default=datetime.now)
    updated_at = Column(DateTime, default=datetime.now, onupdate=datetime.now)
    
    # Relationships
    player = relationship("Player", back_populates="stats")
    
    def __repr__(self):
        return f"<Stat(player_id={self.player_id}, skill='{self.skill_name}', count={self.count})>"

# Initialize the database
def init_db():
    Base.metadata.create_all(engine)

# Database operations
def create_team(team_name):
    """Create a new team"""
    session = Session()
    team = Team(name=team_name)
    session.add(team)
    session.commit()
    team_id = team.id
    session.close()
    return team_id

def add_players_to_team(team_id, player_names):
    """Add multiple players to a team"""
    session = Session()
    for name in player_names:
        player = Player(name=name, team_id=team_id)
        session.add(player)
    session.commit()
    session.close()

def initialize_player_stats(player_id, skill_names):
    """Initialize stats for a player with all skills set to 0"""
    session = Session()
    for skill in skill_names:
        stat = Stat(player_id=player_id, skill_name=skill, count=0)
        session.add(stat)
    session.commit()
    session.close()

def get_team_with_players(team_id):
    """Get team and its players"""
    session = Session()
    team = session.query(Team).filter(Team.id == team_id).first()
    players = session.query(Player).filter(Player.team_id == team_id).all()
    session.close()
    return team, players

def get_player_by_name(name):
    """Get a player by name"""
    session = Session()
    player = session.query(Player).filter(Player.name == name).first()
    session.close()
    return player

def update_player_stat(player_id, skill_name):
    """Increment a specific stat for a player"""
    session = Session()
    
    try:
        # Use SQLAlchemy update statement instead of direct attribute modification
        stmt = (
            update(Stat)
            .where(Stat.player_id == player_id, Stat.skill_name == skill_name)
            .values(count=Stat.count + 1)
        )
        session.execute(stmt)
        session.commit()
        result = True
    except Exception as e:
        print(f"Error updating stat: {e}")
        session.rollback()
        result = False
    finally:
        session.close()
        
    return result

def get_all_stats_for_team(team_id):
    """Get all stats for a team as a pandas DataFrame"""
    session = Session()
    
    # Get players for the team
    players = session.query(Player).filter(Player.team_id == team_id).all()
    player_ids = [p.id for p in players]
    player_names = [p.name for p in players]
    
    # Get all stats for these players
    all_stats = session.query(Stat).filter(Stat.player_id.in_(player_ids)).all()
    
    session.close()
    
    # Create a dictionary to store the stats
    stats_dict = {player_name: {} for player_name in player_names}
    
    # Map player IDs to names
    id_to_name = {p.id: p.name for p in players}
    
    # Fill in the stats
    for stat in all_stats:
        player_name = id_to_name[stat.player_id]
        stats_dict[player_name][stat.skill_name] = stat.count
    
    # Convert to DataFrame
    df = pd.DataFrame.from_dict(stats_dict, orient='index')
    
    # Ensure all columns are present
    for skill in session.query(Stat.skill_name).distinct():
        if skill[0] not in df.columns:
            df[skill[0]] = 0
    
    return df

def get_most_recent_team():
    """Get the most recently created team"""
    session = Session()
    team = session.query(Team).order_by(Team.created_at.desc()).first()
    session.close()
    return team

def save_current_stats(team_id, stats_df):
    """Update the database with the current stats from the DataFrame"""
    session = Session()
    
    try:
        # Get all players for this team
        players = session.query(Player).filter(Player.team_id == team_id).all()
        player_name_to_id = {p.name: p.id for p in players}
        
        # Update stats for each player
        for player_name, row in stats_df.iterrows():
            if player_name in player_name_to_id:
                player_id = player_name_to_id[player_name]
                
                for skill_name, count in row.items():
                    # Use SQLAlchemy update statement 
                    stmt = (
                        update(Stat)
                        .where(Stat.player_id == player_id, Stat.skill_name == skill_name)
                        .values(count=int(count))
                    )
                    result = session.execute(stmt)
                    
                    # If no rows were updated, insert a new stat
                    if result.rowcount == 0:
                        # Create and add new stat object
                        new_stat = Stat(
                            player_id=player_id, 
                            skill_name=skill_name, 
                            count=0  # Will set actual count value after adding to session
                        )
                        session.add(new_stat)
                        session.flush()  # Flush to get the ID
                        
                        # Now update with the correct count
                        stmt = (
                            update(Stat)
                            .where(Stat.id == new_stat.id)
                            .values(count=int(count))
                        )
                        session.execute(stmt)
        
        session.commit()
    except Exception as e:
        print(f"Error saving stats: {e}")
        session.rollback()
    finally:
        session.close()

# Initialize database if this module is run directly
if __name__ == "__main__":
    init_db()