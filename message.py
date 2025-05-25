import base64
from email.utils import parseaddr, parsedate_to_datetime
from datetime import datetime

from bs4 import BeautifulSoup


class Message:
    def __init__(self):
        self.id = None
        self.thread_id = None
        self.sender = {}
        self.recipients = {}
        self.labels = []
        self.subject = None
        self.body = None
        self.size = 0
        self.timestamp = None
        self.is_read = False
        self.is_outgoing = False

    @classmethod
    def from_raw(cls, raw: dict, labels: dict):
        """
        Create a Message object from a raw message.

        Args:
            raw (dict): The raw message.
            labels (dict): The label map.

        Returns:
            Message: The Message object.
        """

        msg = cls()
        msg.parse(raw, labels)
        return msg

    def parse_addresses(self, addresses: str) -> list:
        """
        Parse a list of email addresses.

        Args:
            addresses (str): The list of email addresses to parse.

        Returns:
            list: The parsed email addresses.
        """

        parsed_addresses = []
        for address in addresses.split(","):
            name, email = parseaddr(address)
            if len(email) > 0:
                parsed_addresses.append({"email": email.lower(), "name": name})

        return parsed_addresses

    def decode_body(self, part) -> str:
        """
        Decode the body of a message part.

        Args:
            part (dict): The message part to decode.

        Returns:
            str: The decoded body of the message part.
        """

        if "data" in part["body"]:
            return base64.urlsafe_b64decode(part["body"]["data"]).decode("utf-8")
        elif "parts" in part:
            for subpart in part["parts"]:
                decoded_body = self.decode_body(subpart)
                if decoded_body:
                    return decoded_body

        return ""

    def html2text(self, html: str) -> str:
        """
        Convert HTML to plain text.

        Args:
            html (str): The HTML to convert.

        Returns:
            str: The converted HTML.
        """

        soup = BeautifulSoup(html, features="html.parser")
        return soup.get_text()

    def parse(self, msg: dict, labels: dict) -> None:
        """
        Parses a raw message.

        Args:
            msg (dict): The message to process.
            labels (dict): The label map.

        Returns:
            None
        """

        self.id = msg["id"]
        self.thread_id = msg["threadId"]
        self.size = msg["sizeEstimate"]

        # Use the internal date if available, otherwise use the parsed date.
        # internalDate is the timestamp when the message was received by Gmail.
        if "internalDate" in msg:
            internal_date_secs = int(msg["internalDate"]) / 1000
            self.timestamp = datetime.fromtimestamp(internal_date_secs)

        for header in msg["payload"]["headers"]:
            name = header["name"].lower()
            value = header["value"]
            if name == "from":
                addr = parseaddr(value)
                self.sender = {"name": addr[0], "email": addr[1]}
            elif name == "to":
                self.recipients["to"] = self.parse_addresses(value)
            elif name == "cc":
                self.recipients["cc"] = self.parse_addresses(value)
            elif name == "bcc":
                self.recipients["bcc"] = self.parse_addresses(value)
            elif name == "subject":
                self.subject = value
            elif name == "date" and self.timestamp is None:
                self.timestamp = parsedate_to_datetime(value) if value else None

        # Labels
        if "labelIds" in msg:
            for l in msg["labelIds"]:
                self.labels.append(labels[l])

            self.is_read = "UNREAD" not in msg["labelIds"]
            self.is_outgoing = "SENT" in msg["labelIds"]

        # Extract body
        # For non multipart messages, use the body from the message directly.
        if "body" in msg["payload"]:
            if "data" in msg["payload"]["body"]:
                self.body = base64.urlsafe_b64decode(
                    msg["payload"]["body"]["data"]
                ).decode("utf-8")

                self.body = self.html2text(self.body)

        # For multipart messages, get the body from the parts.
        if "parts" in msg["payload"] and self.body is None:
            for part in msg["payload"]["parts"]:
                if (
                    part["mimeType"] == "text/html"
                    or part["mimeType"] == "text/plain"
                    or part["mimeType"] == "multipart/related"
                    or part["mimeType"] == "multipart/alternative"
                ):
                    self.body = self.decode_body(part)
                    self.body = self.html2text(self.body)

                    if len(self.body) > 0:
                        break
