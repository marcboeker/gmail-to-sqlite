from peewee import IntegrityError

from . import db
from .providers.base import EmailProvider
from .providers.gmail import GmailProvider
from .providers.imap import IMAPProvider


def get_provider(provider_type: str, data_dir: str) -> EmailProvider:
    """
    Get an instance of the appropriate email provider.
    
    Args:
        provider_type (str): The type of provider ('gmail' or 'imap')
        data_dir (str): Path to data directory
        
    Returns:
        EmailProvider: An initialized provider instance
    """
    if provider_type == "gmail":
        provider = GmailProvider()
    elif provider_type == "imap":
        provider = IMAPProvider()
    else:
        raise ValueError(f"Unsupported provider type: {provider_type}")
    
    provider.authenticate(data_dir)
    return provider


def all_messages(provider_type: str, data_dir: str, full_sync=False, clobber=[]) -> int:
    """
    Fetches messages from the email provider.

    Args:
        provider_type (str): The type of provider ('gmail' or 'imap')
        data_dir (str): Path to data directory
        full_sync (bool): Whether to do a full sync or not.
        clobber (List[str]): Fields to update on conflict

    Returns:
        int: The number of messages fetched.
    """
    provider = get_provider(provider_type, data_dir)
    
    # Build query based on existing database state if not full sync
    query = None
    if not full_sync:
        last = db.last_indexed()
        first = db.first_indexed()
        
        if last or first:
            query = provider.build_query(after=last, before=first)
    
    page_token = None
    run = True
    total_messages = 0
    
    while run:
        results = provider.list_messages(query=query, page_token=page_token)

        print(results)

        messages = results.get("messages", [])

        total_messages += len(messages)
        for i, m in enumerate(messages, start=total_messages - len(messages) + 1):
            try:
                msg = provider.get_message(m["id"])
                db.create_message(msg, clobber)
                print(f"Synced message {msg.id} from {msg.timestamp} (Count: {i})")
            except IntegrityError as e:
                print(f"Could not process message {m['id']}: {str(e)}")
            except Exception as e:
                print(f"Could not get message {m['id']}: {str(e)}")
        
        if "nextPageToken" in results and results["nextPageToken"] != None:
            page_token = results["nextPageToken"]
        else:
            run = False
    
    return total_messages


def single_message(provider_type: str, data_dir: str, message_id: str, clobber=[]) -> None:
    """
    Syncs a single message using the provided credentials and message ID.

    Args:
        provider_type (str): The type of provider ('gmail' or 'imap')
        data_dir (str): Path to data directory
        message_id: The ID of the message to fetch.
        clobber (List[str]): Fields to update on conflict

    Returns:
        None
    """
    provider = get_provider(provider_type, data_dir)
    
    try:
        msg = provider.get_message(message_id)
        db.create_message(msg, clobber)
        print(f"Synced message {message_id} from {msg.timestamp}")
    except IntegrityError as e:
        print(f"Could not process message {message_id}: {str(e)}")
    except Exception as e:
        print(f"Could not get message {message_id}: {str(e)}")
