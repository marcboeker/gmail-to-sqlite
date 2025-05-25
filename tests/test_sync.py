import unittest
from unittest.mock import patch, Mock, call

from googleapiclient.errors import HttpError
from peewee import IntegrityError

# Assuming sync.py is in the parent directory or accessible via PYTHONPATH
# Adjust the import path if your project structure is different.
# For this environment, files are at the root of /app
from sync import _fetch_message_details
# We don't import message or db directly, as their methods used by 
# _fetch_message_details will be patched within the 'sync' module's context.


class TestFetchMessageDetails(unittest.TestCase):

    @patch('sync.time.sleep')
    @patch('sync.logging')
    @patch('sync.db.create_message')
    @patch('sync.message.Message.from_raw')
    def test_successful_fetch_first_attempt(self, mock_message_from_raw, mock_db_create_message, mock_logging, mock_sleep):
        mock_service = Mock()
        mock_raw_msg_data = {'id': 'msg1_raw', 'threadId': 'thread1'} # Sample raw data
        
        # Configure the service mock
        mock_get_request = Mock()
        mock_get_request.execute.return_value = mock_raw_msg_data
        mock_service.users.return_value.messages.return_value.get.return_value = mock_get_request

        mock_msg_object = Mock(id='msg1_processed', timestamp='2023-01-01T12:00:00Z')
        mock_message_from_raw.return_value = mock_msg_object

        result = _fetch_message_details(mock_service, 'id1', {'INBOX'})

        self.assertTrue(result)
        mock_service.users().messages().get.assert_called_once_with(userId='me', id='id1')
        mock_message_from_raw.assert_called_once_with(mock_raw_msg_data, {'INBOX'})
        mock_db_create_message.assert_called_once_with(mock_msg_object)
        mock_logging.info.assert_called_once_with(
            f"Successfully synced message msg1_processed (Original ID: id1) from 2023-01-01T12:00:00Z"
        )
        mock_sleep.assert_not_called()
        mock_logging.warning.assert_not_called()
        mock_logging.error.assert_not_called()

    @patch('sync.time.sleep')
    @patch('sync.logging')
    @patch('sync.db.create_message')
    @patch('sync.message.Message.from_raw')
    def test_retry_on_timeout_then_success(self, mock_message_from_raw, mock_db_create_message, mock_logging, mock_sleep):
        mock_service = Mock()
        mock_raw_msg_data = {'id': 'msg2_raw', 'threadId': 'thread2'}
        
        mock_get_request = Mock()
        # First call raises TimeoutError, second call succeeds
        mock_get_request.execute.side_effect = [
            TimeoutError("Simulated timeout"),
            mock_raw_msg_data 
        ]
        mock_service.users.return_value.messages.return_value.get.return_value = mock_get_request

        mock_msg_object = Mock(id='msg2_processed', timestamp='2023-01-02T12:00:00Z')
        mock_message_from_raw.return_value = mock_msg_object

        result = _fetch_message_details(mock_service, 'id2', {})

        self.assertTrue(result)
        self.assertEqual(mock_service.users().messages().get().execute.call_count, 2)
        mock_logging.warning.assert_called_once_with(
            "Attempt 1/3 failed for message id2 due to timeout. Retrying in 5s..."
        )
        mock_sleep.assert_called_once_with(5) # 5 is retry_delay_seconds in sync.py
        mock_db_create_message.assert_called_once_with(mock_msg_object)
        mock_logging.info.assert_called_once() # For the successful sync
        mock_logging.error.assert_not_called()


    @patch('sync.time.sleep')
    @patch('sync.logging')
    @patch('sync.db.create_message')
    @patch('sync.message.Message.from_raw')
    def test_failure_after_max_retries_http_error(self, mock_message_from_raw, mock_db_create_message, mock_logging, mock_sleep):
        mock_service = Mock()
        
        # Mock HttpError response object
        mock_http_error_response = Mock(status=503)
        http_error_instance = HttpError(resp=mock_http_error_response, content=b"Service Unavailable")

        mock_get_request = Mock()
        mock_get_request.execute.side_effect = http_error_instance # Raise HttpError consistently
        mock_service.users.return_value.messages.return_value.get.return_value = mock_get_request
        
        # max_retries is 3 in _fetch_message_details
        expected_attempts = 3

        result = _fetch_message_details(mock_service, 'id3', {})

        self.assertFalse(result)
        self.assertEqual(mock_service.users().messages().get().execute.call_count, expected_attempts)
        
        # Check logging.warning calls
        expected_warning_calls = [
            call(f"Attempt 1/{expected_attempts} failed for message id3 due to server error 503. Retrying in 5s..."),
            call(f"Attempt 2/{expected_attempts} failed for message id3 due to server error 503. Retrying in 5s...")
        ]
        mock_logging.warning.assert_has_calls(expected_warning_calls)
        self.assertEqual(mock_logging.warning.call_count, expected_attempts - 1) # Warnings for retries, not the final one

        # Check time.sleep calls
        self.assertEqual(mock_sleep.call_count, expected_attempts - 1) # Sleep before each retry

        # Check logging.error call for the final failure
        mock_logging.error.assert_called_once_with(
            f"Failed to fetch message id3 after {expected_attempts} attempts due to HttpError 503: {str(http_error_instance)}"
        )
        mock_db_create_message.assert_not_called()
        mock_message_from_raw.assert_not_called()


    @patch('sync.time.sleep')
    @patch('sync.logging')
    @patch('sync.db.create_message')
    @patch('sync.message.Message.from_raw')
    def test_non_retryable_integrity_error(self, mock_message_from_raw, mock_db_create_message, mock_logging, mock_sleep):
        mock_service = Mock()
        mock_raw_msg_data = {'id': 'msg4_raw', 'threadId': 'thread4'}

        mock_get_request = Mock()
        mock_get_request.execute.return_value = mock_raw_msg_data
        mock_service.users.return_value.messages.return_value.get.return_value = mock_get_request

        mock_msg_object = Mock(id='msg4_processed', timestamp='2023-01-04T12:00:00Z')
        mock_message_from_raw.return_value = mock_msg_object

        integrity_error_instance = IntegrityError("Simulated DB integrity error")
        mock_db_create_message.side_effect = integrity_error_instance

        result = _fetch_message_details(mock_service, 'id4', {})

        self.assertFalse(result)
        mock_service.users().messages().get.assert_called_once_with(userId='me', id='id4')
        mock_message_from_raw.assert_called_once_with(mock_raw_msg_data, {})
        mock_db_create_message.assert_called_once_with(mock_msg_object)
        
        mock_logging.error.assert_called_once_with(
            f"Could not process message id4 due to integrity error (will not retry): {str(integrity_error_instance)}"
        )
        mock_sleep.assert_not_called()
        mock_logging.warning.assert_not_called()
        # logging.info for successful sync should not be called
        mock_logging.info.assert_not_called()

if __name__ == '__main__':
    unittest.main()
