# Gmail to SQLite

A robust Python application that syncs Gmail messages to a local SQLite database for analysis and archival purposes.

## Features

- **Incremental Sync**: Only downloads new messages by default
- **Full Sync**: Option to download all messages and detect deletions
- **Parallel Processing**: Multi-threaded message fetching for improved performance
- **Robust Error Handling**: Automatic retries with exponential backoff
- **Graceful Shutdown**: Handles interruption signals cleanly
- **Type Safety**: Comprehensive type hints throughout the codebase

## Installation

### Prerequisites

- Python 3.8 or higher
- Google Cloud Project with Gmail API enabled
- OAuth 2.0 credentials file (`credentials.json`)

### Setup

1. **Clone the repository:**

   ```bash
   git clone https://github.com/marcboeker/gmail-to-sqlite.git
   cd gmail-to-sqlite
   ```

2. **Install dependencies:**

   ```bash
   # Using uv
   uv sync
   ```

3. **Set up Gmail API credentials:**
   - Go to the [Google Cloud Console](https://console.cloud.google.com/)
   - Create a new project or select an existing one
   - Enable the Gmail API
   - Create OAuth 2.0 credentials (Desktop application)
   - Download the credentials file and save it as `credentials.json` in the project root

## Usage

### Basic Commands

You can run the application using either `python` directly or via `uv`:

```bash
# Incremental sync (default)
python main.py sync --data-dir ./data
# or: uv run main.py sync --data-dir ./data

# Full sync with deletion detection
python main.py sync --data-dir ./data --full-sync

# Sync a specific message
python main.py sync-message --data-dir ./data --message-id MESSAGE_ID

# Detect and mark deleted messages only
python main.py sync-deleted-messages --data-dir ./data

# Use custom number of worker threads
python main.py sync --data-dir ./data --workers 8

# Get help
python main.py --help
python main.py sync --help
```

### Command Line Arguments

- `command`: Required. One of `sync`, `sync-message`, or `sync-deleted-messages`
- `--data-dir`: Required. Directory where the SQLite database will be stored
- `--full-sync`: Optional. Forces a complete sync of all messages
- `--message-id`: Required for `sync-message`. The ID of a specific message to sync
- `--workers`: Optional. Number of worker threads (default: number of CPU cores)
- `--help`: Show help information for commands and options

### Graceful Shutdown

The application supports graceful shutdown when you press CTRL+C:

1. Stops accepting new tasks
2. Waits for currently running tasks to complete
3. Saves progress of completed work
4. Exits cleanly

Pressing CTRL+C a second time will force an immediate exit.

## Database Schema

The application creates a SQLite database with the following schema:

| Field        | Type     | Description                      |
| ------------ | -------- | -------------------------------- |
| message_id   | TEXT     | Unique Gmail message ID          |
| thread_id    | TEXT     | Gmail thread ID                  |
| sender       | JSON     | Sender information (name, email) |
| recipients   | JSON     | Recipients by type (to, cc, bcc) |
| labels       | JSON     | Array of Gmail labels            |
| subject      | TEXT     | Message subject                  |
| body         | TEXT     | Message body (plain text)        |
| size         | INTEGER  | Message size in bytes            |
| timestamp    | DATETIME | Message timestamp                |
| is_read      | BOOLEAN  | Read status                      |
| is_outgoing  | BOOLEAN  | Whether sent by user             |
| is_deleted   | BOOLEAN  | Whether deleted from Gmail       |
| last_indexed | DATETIME | Last sync timestamp              |

## Example queries

### Get the number of emails per sender

```sql
SELECT sender->>'$.email', COUNT(*) AS count
FROM messages
GROUP BY sender->>'$.email'
ORDER BY count DESC
```

### Show the number of unread emails by sender

This is great to determine who is spamming you the most with uninteresting emails.

```sql
SELECT sender->>'$.email', COUNT(*) AS count
FROM messages
WHERE is_read = 0
GROUP BY sender->>'$.email'
ORDER BY count DESC
```

### Get the number of emails for a specific period

- For years: `strftime('%Y', timestamp)`
- For months in a year: `strftime('%m', timestamp)`
- For days in a month: `strftime('%d', timestamp)`
- For weekdays: `strftime('%w', timestamp)`
- For hours in a day: `strftime('%H', timestamp)`

```sql
SELECT strftime('%Y', timestamp) AS period, COUNT(*) AS count
FROM messages
GROUP BY period
ORDER BY count DESC
```

### Find all newsletters and group them by sender

This is an amateurish way to find all newsletters and group them by sender. It's not perfect, but it's a start. You could also use

```sql
SELECT sender->>'$.email', COUNT(*) AS count
FROM messages
WHERE body LIKE '%newsletter%' OR body LIKE '%unsubscribe%'
GROUP BY sender->>'$.email'
ORDER BY count DESC
```

### Show who has sent the largest emails in MB

```sql
SELECT sender->>'$.email', sum(size)/1024/1024 AS size
FROM messages
GROUP BY sender->>'$.email'
ORDER BY size DESC
```

### Count the number of emails that I have sent to myself

```sql
SELECT count(*)
FROM messages
WHERE EXISTS (
  SELECT 1
  FROM json_each(messages.recipients->'$.to')
  WHERE json_extract(value, '$.email') = 'foo@example.com'
)
AND sender->>'$.email' = 'foo@example.com'
```

### List the senders who have sent me the largest total volume of emails in megabytes

```sql
SELECT sender->>'$.email', sum(size)/1024/1024 as total_size
FROM messages
WHERE is_outgoing=false
GROUP BY sender->>'$.email'
ORDER BY total_size DESC
```

### Find all deleted messages

```sql
SELECT message_id, subject, timestamp
FROM messages
WHERE is_deleted=1
ORDER BY timestamp DESC
```
