# Gmail to SQLite

This is a script to download emails from Gmail and store them in a SQLite database for further analysis. I find it extremely useful to have all my emails in a database to run queries on them. For example, I can find out how many emails I received per sender, which emails take the most space and which emails from which sender I never read.

## Installation

1. Clone this repository: `git clone https://github.com/marcboeker/gmail-to-sqlite.git`.
2. Install the requirements: `pip install -r requirements.txt`
3. Create a Google Cloud project [here](https://console.cloud.google.com/projectcreate).
4. Open [Gmail in API & Services](https://console.cloud.google.com/apis/library/gmail.googleapis.com) and activate the Gmail API.
5. Open the [OAuth consent screen](https://console.cloud.google.com/apis/credentials/consent) and create a new consent screen. You only need to provide a name and contact data.
6. Next open [Create OAuth client ID](https://console.cloud.google.com/apis/credentials/oauthclient) and create credentials for a `Desktop app`. Download the credentials file and save it under `credentials.json` in the root of this repository.

## Usage

1. Run the script: `python main.py <project-name>` where `<project-name>` is the name of the project e.g. `bob`. This will create a SQLite database in `<project-name>/messages.db` and store the user credentials under `<project-name>/credentials.json`.
2. After the script has finished, you can query the database using e.g. the `sqlite3` command line tool: `sqlite3 <project-name>/messages.db`.
3. You can run the script again to download new emails. It will only add emails that are not already in the database and update the `last_indexed` timestamp and the `is_read` flag. At the moment, the script will sync all emails again. This will be improved in the future.

## Note

As the script also stores the raw email in the database, the database can become quite large. If you don't need the raw emails, you can remove the `raw` column from the `messages` table.

## Schema

```sql
CREATE TABLE IF NOT EXISTS "messages" (
    "id" INTEGER NOT NULL PRIMARY KEY, -- internal id
    "message_id" TEXT NOT NULL, -- Gmail message id
    "sender" TEXT NOT NULL, -- Full sender in the form "Foo Bar <foo@example.com>"
    "sender_name" TEXT NOT NULL, -- Extracted name: Foo Bar
    "sender_email" TEXT NOT NULL, -- Extracted email address: foo@example.com
    "recipients" JSON NOT NULL, -- JSON array: [{"email": "foo@example.com", "name": "Foo Bar"}, ...]
    "subject" TEXT NOT NULL, -- Subject of the email
    "body" TEXT NOT NULL, -- Extracted body either als HTML or plain text
    "raw" JSON NOT NULL, -- Raw email from Gmail fetch response
    "size" INTEGER NOT NULL, -- Size reported by Gmail
    "timestamp" DATETIME NOT NULL, -- When the email was sent/received
    "is_read" INTEGER NOT NULL, -- 0=Unread, 1=Read
    "last_indexed" DATETIME NOT NULL -- Timestamp when the email was last seen on the server
);
```

## Example queries

### Get the number of emails per sender

```sql
SELECT sender_email, COUNT(*) AS count
FROM messages
GROUP BY sender
ORDER BY count DESC;
```

### Show the number of unread emails by sender

This is great to determine who is spamming you the most with uninteresting emails.

```sql
SELECT sender_email, COUNT(*) AS count
FROM messages
WHERE is_read = 0
GROUP BY sender_email
ORDER BY count DESC;
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
ORDER BY count DESC;
```

### Find all newsletters and group them by sender

This is an amateurish way to find all newsletters and group them by sender. It's not perfect, but it's a start. You could also use

```sql
SELECT sender_email, COUNT(*) AS count
FROM messages
WHERE body LIKE '%newsletter%' OR body LIKE '%unsubscribe%'
GROUP BY sender_email
ORDER BY count DESC;
```

### Show who has sent the largest emails (incl. attachments)

```sql
SELECT sender_email, sum(size) AS size
FROM messages
GROUP BY sender_email
ORDER BY size DESC
```

## Roadmap

- [ ] When syncing again, use the timestaxmp of the newest email in the database as the `after` parameter for the Gmail API. This will prevent iteration over all emails again.
- [ ] Add a flag to prevent storing raw emails in the database to save space.
- [ ] Detect deleted emails and mark them as deleted in the database.
- [ ] Add proper commandline interface.
