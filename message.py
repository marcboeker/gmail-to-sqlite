import base64
from email.utils import parseaddr, parsedate_to_datetime

from bs4 import BeautifulSoup


class Message:
    def __init__(self):
        self.id = None
        self.thread_id = None
        self.sender = {}
        self.recipients = []
        self.subject = None
        self.body = None
        self.size = 0
        self.timestamp = None
        self.is_read = False
        self.is_outgoing = False

    @classmethod
    def from_raw(cls, raw: dict):
        """
        Create a Message object from a raw message.

        Args:
            raw (dict): The raw message.

        Returns:
            Message: The Message object.
        """

        msg = cls()
        msg.parse(raw)
        return msg

    def parse_addresses(self, addresses: str, type: str) -> list:
        """
        Parse a list of email addresses.

        Args:
            addresses (str): The list of email addresses to parse.
            type (str): The type of the email addresses (to, cc, bcc).

        Returns:
            list: The parsed email addresses.
        """

        parsed_addresses = []
        for address in addresses.split(";"):
            name, email = parseaddr(address)
            if len(email) > 0:
                parsed_addresses.append(
                    {"email": email.lower(), "name": name, "type": type}
                )

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

    def parse(self, msg: dict) -> None:
        """
        Parses a raw message.

        Args:
            msg (dict): The message to process.

        Returns:
            None
        """

        self.id = msg["id"]
        self.thread_id = msg["threadId"]
        self.size = msg["sizeEstimate"]

        for header in msg["payload"]["headers"]:
            name = header["name"].lower()
            value = header["value"]
            if name == "from":
                addr = parseaddr(value)
                self.sender = {"name": addr[0], "email": addr[1]}
            elif name == "to":
                self.recipients.extend(self.parse_addresses(value, "to"))
            elif name == "cc":
                self.recipients.extend(self.parse_addresses(value, "cc"))
            elif name == "bcc":
                self.recipients.extend(self.parse_addresses(value, "bcc"))
            elif name == "subject":
                self.subject = value
            elif name == "date":
                self.timestamp = parsedate_to_datetime(value)

        # Labels
        if "labelIds" in msg:
            self.labels = msg["labelIds"]
            if "UNREAD" in self.labels:
                self.is_read = False
            else:
                self.is_read = True

            if "SENT" in self.labels:
                self.is_outgoing = True

        # Extract body
        # For non multipart messages, use the body from the message directly.
        if "body" in msg["payload"]:
            if "data" in msg["payload"]["body"]:
                self.body = base64.urlsafe_b64decode(
                    msg["payload"]["body"]["data"]
                ).decode("utf-8")

                if (
                    "mimeType" in msg["payload"]["body"]
                    and msg["payload"]["mimeType"] == "text/html"
                ):
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

                    if part["mimeType"] == "text/html":
                        self.body = self.html2text(self.body)

                    if len(self.body) > 0:
                        break
