import os, sys, asyncio, json
sys.path.insert(0, os.path.abspath('src'))
from satmi_agent.persistence import SessionLocal, ConversationIntentLabelRecord, persistence_service
from satmi_agent.llm import classify_conversation_intent_with_llm

def run():
    with SessionLocal() as session:
        records = session.query(ConversationIntentLabelRecord).filter((ConversationIntentLabelRecord.intent_subcategory == None) | (ConversationIntentLabelRecord.intent_subcategory == "")).all()
        print(f"Found {len(records)} records to backfill.")
        for r in records:
            transcript = persistence_service.list_conversation_events_for_classification(r.conversation_id)
            if not transcript: continue
            
            transcript_dicts = [{"role": t.role, "content": t.message} for t in transcript]
            res = classify_conversation_intent_with_llm(transcript=transcript_dicts, source_version="v1")
            if res:
                r.intent_label = res.get("intent_label", r.intent_label)
                r.intent_subcategory = res.get("intent_subcategory", "")
                r.raw_intent_label = res.get("raw_intent_label", "")
                session.commit()
                print(f"Updated {r.conversation_id} -> {r.intent_label} | {r.intent_subcategory}")

run()
