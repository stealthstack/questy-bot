import csv
import json
import os

print(f"📁 Current directory: {os.getcwd()}")
print(f"📋 Files here: {os.listdir()}")

csv_filename = 'speedrun_data.csv'
if csv_filename not in os.listdir():
    print(f"❌ File '{csv_filename}' not found!")
    exit()

speedrun_list = []

with open(csv_filename, 'r', encoding='utf-8') as csv_file:
    csv_reader = csv.DictReader(csv_file, delimiter=',')
    
    print(f"✅ Found columns: {csv_reader.fieldnames}")
    
    for row in csv_reader:
        # Clean empty bingo bonuses
        bingo_bonuses = []
        for i in range(1, 4):
            bingo_key = f"Bingo {i}"
            if bingo_key in row and row[bingo_key].strip():
                bingo_bonuses.append(row[bingo_key].strip())
        
        # If no bingos, add placeholder
        if not bingo_bonuses:
            bingo_bonuses = ["—", "—", "—"]
        
        # Build the entry WITH CATEGORY
        speedrun_entry = {
            "time": row["Time"],
            "runner": row["Runner"],
            "pokemon": row["Pokemon"],
            "category": row.get("Category", "12-Boss"),  # Default if not present
            "overall_iv": row["Overall IV"],
            "atk": int(row["ATK"]),
            "atk_total": int(row["ATK Total w/stones"]),
            "hp": int(row["HP"]),
            "move_stones": [
                row.get("Stone 1", "").strip(),
                row.get("Stone 2", "").strip(),
                row.get("Stone 3", "").strip()
            ],
            "bingo_bonuses": bingo_bonuses,
            "status": row["Status"],
            "video_link": row.get("Video", "").strip()
        }
        speedrun_list.append(speedrun_entry)

# Save to JSON
with open('speedrun_data.json', 'w', encoding='utf-8') as json_file:
    json.dump(speedrun_list, json_file, indent=2, ensure_ascii=False)

print(f"✅ Converted {len(speedrun_list)} records")
print("📁 File saved: speedrun_data.json")