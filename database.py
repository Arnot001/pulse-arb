from sqlalchemy import create_engine, Column, Integer, String, Float, Text, DateTime
from sqlalchemy.orm import sessionmaker, declarative_base
from datetime import datetime
import json

Base = declarative_base()
engine = create_engine("sqlite:///arbs.db", echo=False)
Session = sessionmaker(bind=engine)

class StoredArb(Base):
    tablename = "arbs"
    id = Column(Integer, primary_key=True)
    event_id = Column(String)
    event = Column(String)
    commence_time = Column(String)
    market = Column(String)
    profit_percent = Column(Float)
    book_percentage = Column(Float)
    opportunity_type = Column(String)
    opportunity_score = Column(Integer)


    details = Column(Text)
    timestamp = Column(DateTime, default=datetime.utcnow)
    

Base.metadata.create_all(engine)

def store_arbs(arbs: list):
    session = Session()
    for arb in arbs:
        existing = session.query(StoredArb).filter_by(event_id=arb.event_id, market=arb.market).first()
        if not existing:
            new_arb = StoredArb(
                book_percentage=arb.book_percentage,
                opportunity_type=arb.opportunity_type,
                opportunity_score=arb.opportunity_score,
                event_id=arb.event_id,
                event=arb.event,
                commence_time=arb.commence_time,
                market=arb.market,
                profit_percent=arb.profit_percent,
                details=json.dumps(arb.model_dump()),
            )
            session.add(new_arb)
    session.commit()
    session.close()

def get_recent_arbs(limit=20):
    session = Session()
    arbs = session.query(StoredArb).order_by(StoredArb.timestamp.desc()).limit(limit).all()
    session.close()
    return arbs

