# Gmail to SQLite

This is a script to download emails from Gmail and store them in a SQLite database for further analysis. I find it extremely useful to have all my emails in a database to run queries on them. For example, I can find out how many emails I received per sender, which emails take the most space, and which emails from which sender I never read.

## Installation

1. Clone this repository: `git clone https://github.com/marcboeker/gmail-to-sqlite.git`.
2. Install the requirements: `pip install -r requirements.txt`
3. Create a Google Cloud project [here](https://console.cloud.google.com/projectcreate).
4. Open [Gmail in API & Services](https://console.cloud.google.com/apis/library/gmail.googleapis.com) and activate the Gmail API.
5. Open the [OAuth consent screen](https://console.cloud.google.com/apis/credentials/consent) and create a new consent screen. You only need to provide a name and contact data.
6. Next open [Create OAuth client ID](https://console.cloud.google.com/apis/credentials/oauthclient) and create credentials for a `Desktop app`. Download the credentials file and save it under `credentials.json` in the root of this repository.

Here is a detailed guide on how to create the credentials: [https://developers.google.com/gmail/api/quickstart/python#set_up_your_environment](https://developers.google.com/gmail/api/quickstart/python#set_up_your_environment).

## Usage

### Sync all emails

1. Run the script: `python main.py sync --data-dir path/to/your/data` where `--<data-dir>` is the path where all data is stored. This creates a SQLite database in `<data-dir>/messages.db` and stores the user credentials under `<data-dir>/credentials.json`.
2. After the script has finished, you can query the database using, for example, the `sqlite3` command line tool: `sqlite3 <data-dir>/messages.db`.
3. You can run the script again to sync all new messages. Provide `--full-sync` to force a full sync. However, this will only update the read status, the labels, and the last indexed timestamp for existing messages.

### Sync a single message

`python main.py sync-message --data-dir path/to/your/data --message-id <message-id>`

## Commandline parameters

```
usage: main.py [-h] [--data-dir DATA_DIR] [--update] {sync, sync-message}

Main commands:
sync                    Sync emails from Gmail to the database.
sync-message            Sync a single message from Gmail to the database.

--data-dir DATA_DIR     Path to the directory where all data is stored.
--full-sync             Force a full sync.
--message-id MESSAGE_ID Sync only the message with the given message id.
```

## Schema

```sql
CREATE TABLE IF NOT EXISTS "messages" (
    "id" INTEGER NOT NULL PRIMARY KEY, -- internal id
    "message_id" TEXT NOT NULL, -- Gmail message id
    "thread_id" TEXT NOT NULL, -- Gmail thread id
    "sender" JSON NOT NULL, -- Sender as JSON in the form {"name": "Foo Bar", "email": "foo@example.com"}
    "recipients" JSON NOT NULL, -- JSON object: {
      -- "to": [{"email": "foo@example.com", "name": "Foo Bar"}, ...],
      -- "cc": [{"email": "foo@example.com", "name": "Foo Bar"}, ...],
      -- "bcc": [{"email": "foo@example.com", "name": "Foo Bar"}, ...]
    --}
    "labels" JSON NOT NULL, -- JSON array: ["INBOX", "UNREAD", ...]
    "subject" TEXT NOT NULL, -- Subject of the email
    "body" TEXT NOT NULL, -- Extracted body either als HTML or plain text
    "size" INTEGER NOT NULL, -- Size reported by Gmail
    "timestamp" DATETIME NOT NULL, -- When the email was sent/received
    "is_read" INTEGER NOT NULL, -- 0=Unread, 1=Read
    "is_outgoing" INTEGER NOT NULL, -- 0=Incoming, 1=Outgoing
    "last_indexed" DATETIME NOT NULL -- Timestamp when the email was last seen on the server
);
```

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

## Roadmap

- [ ] Detect deleted emails and mark them as deleted in the database.
