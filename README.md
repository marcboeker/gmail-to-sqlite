# Mail to SQLite

This is a loosely-coded just-for-fun script to download emails from a variety 
of providers and store them in a SQLite database for further analysis. It's 
useful if you want to run SQL queries against your email (and who doesn't!) 
It's also useful for hooking up an LLM with email, with a minimum of fuss. Try 
combining it with [lectic](https://github.com/gleachkr/lectic), which has 
built-in SQLite support.

## Installation

1. With nix: `nix profile install github:gleachkr/mail-to-sqlite`. 
   After installation, the command `mail_to_sqlite` will be available.

2. With pip: if you want to do this, just post an issue and I'll make 
   it possible.

## Authentication Setup

### For Gmail

You'll need OAuth credentials from Google for a *Desktop App*:

1. Visit the [Google Cloud Console](https://console.cloud.google.com/)
2. Create a new project or select an existing one
3. Enable the Gmail API for your project
4. Create OAuth credentials for a Desktop application
5. Download the credentials JSON file, and keep it in your `--data-dir` 
   (see below)

For detailed instructions, follow Google's [Python Quickstart 
Guide](https://developers.google.com/gmail/api/quickstart/python#set_up_your_environment).

### For IMAP Providers

For IMAP servers, you'll need:
- Server address and port
- Your username/email
- Your password or an app-specific password

Put them in a JSON file called imap_credentials.json, and keep that in 
the `--data-dir` that you pass to the program.

## Usage

### Basic Command Structure

```
mail_to_sqlite COMMAND [OPTIONS]
```

### Syncing All Messages

```
mail_to_sqlite --data-dir PATH/TO/DATA --provider [gmail|imap]
```

This creates and updates a SQLite database at `PATH/TO/DATA/messages.db`. On 
the first sync it will pull down everything. Subsequent syncs are incremental 
(IMAP only lets you specify a time range with day-level granularity though, so 
you might still pull down some already downloaded emails).

### Syncing a Single Message

```
mail_to_sqlite sync-message --data-dir PATH/TO/DATA --message-id MESSAGE_ID
```

### Command-line Parameters

```
usage: mail_to_sqlite [-h] --data-dir DATA_DIR [--full-sync] 
                      [--message-id MESSAGE_ID] [--clobber [ATTR ...]]
                      [--provider {gmail,imap}]

positional arguments:
  command                The command to run: {sync, sync-message}

options:
  -h, --help                Show this help message and exit
  --data-dir DATA_DIR       Directory where data should be stored
  --full-sync               Force a full sync of all messages
  --message-id MESSAGE_ID   The ID of the message to sync
  --clobber [ATTR ...]      Attributes to overwrite on existing messages
  --provider {gmail,imap}   Email provider to use (default: gmail)
```

## Database Schema

```sql
CREATE TABLE IF NOT EXISTS "messages" (
    "id" INTEGER NOT NULL PRIMARY KEY, 
    "message_id" TEXT NOT NULL,
    "thread_id" TEXT NOT NULL,
    "sender" JSON NOT NULL, 
    "recipients" JSON NOT NULL,
    "labels" JSON NOT NULL,
    "subject" TEXT NOT NULL,
    "body" TEXT NOT NULL,
    "size" INTEGER NOT NULL,
    "timestamp" DATETIME NOT NULL,
    "is_read" INTEGER NOT NULL,
    "is_outgoing" INTEGER NOT NULL,
    "last_indexed" DATETIME NOT NULL
);
```

## Example Queries

### Most Frequent Senders

```sql
SELECT sender->>'$.email', COUNT(*) AS count
FROM messages
GROUP BY sender->>'$.email'
ORDER BY count DESC
LIMIT 20;
```

### Unread Emails by Sender

```sql
SELECT sender->>'$.email', COUNT(*) AS count
FROM messages
WHERE is_read = 0
GROUP BY sender->>'$.email'
ORDER BY count DESC;
```

### Email Volume by Time Period

```sql
-- For yearly statistics
SELECT strftime('%Y', timestamp) AS year, COUNT(*) AS count
FROM messages
GROUP BY year
ORDER BY year DESC;
```

### Storage Usage by Sender (MB)

```sql
SELECT sender->>'$.email', sum(size)/1024/1024 AS size_mb
FROM messages
GROUP BY sender->>'$.email'
ORDER BY size_mb DESC
LIMIT 20;
```

### Potential Newsletters

```sql
SELECT sender->>'$.email', COUNT(*) AS count
FROM messages
WHERE body LIKE '%unsubscribe%' 
GROUP BY sender->>'$.email'
ORDER BY count DESC;
```

### Self-Emails

```sql
SELECT count(*)
FROM messages
WHERE json_extract(sender, '$.email') IN (
  SELECT json_extract(value, '$.email')
  FROM json_each(messages.recipients->'$.to')
);
```

## Advanced Usage

### Targeted Sync with Specific Fields

If you want to update only specific attributes of existing messages:

```
mail_to_sqlite sync --data-dir PATH/TO/DATA --clobber labels is_read
```

### Periodic Syncing

For regular updates, consider setting up a cron job:

```
# Update email database every hour
0 * * * * mail_to_sqlite sync --data-dir ~/mail-data
```
## Contributing

Contributions are welcome! Please feel free to submit a Pull Request.

## License

This project is licensed under the MIT License - see the LICENSE file for 
details. Thanks to @marcboeker for [the original 
gmail-to-sqlite](https://github.com/marcboeker/gmail-to-sqlite).
