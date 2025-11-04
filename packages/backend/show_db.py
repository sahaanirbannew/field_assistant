import argparse
import psycopg2
import psycopg2.extras

# --- Import from our new db.py file ---
import db

def print_summary(cur):
    """Prints a summary of the database contents."""
    cur.execute("SELECT COUNT(*) FROM users;")
    user_count = cur.fetchone()[0]
    cur.execute("SELECT COUNT(*) FROM messages;")
    message_count = cur.fetchone()[0]
    cur.execute("SELECT COUNT(*) FROM media;")
    media_count = cur.fetchone()[0]
    
    print("DB SUMMARY")
    print("----------")
    print(f"Users:    {user_count}")
    print(f"Messages: {message_count}")
    print(f"Media:    {media_count}")
    print("\n" + "="*40 + "\n")

def print_messages_for_user(cur, user, limit):
    """Fetches and prints messages for a specific user."""
    # This query joins messages with their associated media
    cur.execute(
        """
        SELECT 
            m.id, m.telegram_message_id, m.update_id, m.chat_id, m.timestamp, m.text,
            COALESCE(
                (SELECT jsonb_agg(med.*) FROM media med WHERE med.message_id = m.id), 
                '[]'::jsonb
            ) as media
        FROM 
            messages m
        WHERE 
            m.user_id = %s
        ORDER BY 
            m.timestamp DESC
        LIMIT %s;
        """,
        (user['id'], limit)
    )
    
    messages = cur.fetchall()
    
    for msg in messages:
        print(f"  Message id={msg['id']} telegram_message_id={msg['telegram_message_id']} timestamp={msg['timestamp']}")
        
        if msg['text']:
            text = msg['text'].replace('\n', ' ')[:80] # Truncate long text
            print(f"    text: {text}...")
        
        # Print media associated with the message
        for media_item in msg['media']:
            print(f"    - media id={media_item['id']} type={media_item['media_type']} name='{media_item['file_name']}'")

def main():
    parser = argparse.ArgumentParser(description="View data from the Field Assistant DB.")
    parser.add_argument(
        "-u", "--user", 
        type=int, 
        metavar="TELEGRAM_ID",
        help="Filter by a specific Telegram User ID."
    )
    parser.add_argument(
        "-l", "--limit", 
        type=int, 
        default=5, 
        help="Number of messages to show per user (default: 5)."
    )
    args = parser.parse_args()

    conn = db.get_conn()
    
    try:
        # Use DictCursor to get results as dictionaries (like { 'column_name': 'value' })
        with conn.cursor(cursor_factory=psycopg2.extras.DictCursor) as cur:
            
            if args.user:
                # --- Show details for a SINGLE user ---
                cur.execute("SELECT * FROM users WHERE telegram_user_id = %s;", (args.user,))
                user = cur.fetchone()
                
                if not user:
                    print(f"Error: User with Telegram ID {args.user} not found.")
                    return
                
                print(f"Showing last {args.limit} messages for user {user['first_name']} (Telegram ID: {user['telegram_user_id']}):")
                print_messages_for_user(cur, user, args.limit)

            else:
                # --- Show summary for ALL users ---
                print_summary(cur)
                
                cur.execute("SELECT * FROM users ORDER BY id;")
                users = cur.fetchall()
                
                for user in users:
                    print(f"User DB id={user['id']}  telegram_user_id={user['telegram_user_id']}  name='{user['first_name']}'  username='{user['username']}'")
                    print_messages_for_user(cur, user, args.limit)
                    print("-" * 20) # Separator
                    
    except Exception as e:
        print(f"An error occurred: {e}")
    finally:
        conn.close()

if __name__ == "__main__":
    main()