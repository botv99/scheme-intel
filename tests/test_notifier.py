"""
Unit tests for notifier module.
"""
import pytest
from unittest.mock import patch, Mock
from requests.exceptions import Timeout, ConnectionError

from scheme_intel.notifier import send_telegram, validate_telegram_config
from scheme_intel.exceptions import TelegramError


class TestSendTelegram:
    """Tests for Telegram sending."""
    
    @patch.dict('os.environ', {'TELEGRAM_BOT_TOKEN': 'test_token', 'TELEGRAM_CHAT_ID': '123456'})
    def test_send_telegram_success_single_chat(self):
        """Test successful send to single chat."""
        with patch('scheme_intel.notifier.requests.post') as mock_post:
            mock_response = Mock()
            mock_response.raise_for_status = Mock()
            mock_post.return_value = mock_response
            
            result = send_telegram("Test message")
            
            assert result is True
            mock_post.assert_called_once()
            call_args = mock_post.call_args
            assert "123456" in str(call_args)
    
    @patch.dict('os.environ', {'TELEGRAM_BOT_TOKEN': 'test_token', 'TELEGRAM_CHAT_ID': '123456,789012'})
    def test_send_telegram_success_multiple_chats(self):
        """Test successful send to multiple chats."""
        with patch('scheme_intel.notifier.requests.post') as mock_post:
            mock_response = Mock()
            mock_response.raise_for_status = Mock()
            mock_post.return_value = mock_response
            
            result = send_telegram("Test message")
            
            assert result is True
            # Should be called twice (once for each chat)
            assert mock_post.call_count == 2
    
    @patch.dict('os.environ', {}, clear=True)
    def test_send_telegram_no_token(self):
        """Test when bot token is not configured."""
        result = send_telegram("Test message")
        
        assert result is False
    
    @patch.dict('os.environ', {'TELEGRAM_BOT_TOKEN': 'test_token'})
    def test_send_telegram_no_chat_id(self):
        """Test when chat ID is not configured."""
        result = send_telegram("Test message")
        
        assert result is False
    
    @patch.dict('os.environ', {'TELEGRAM_BOT_TOKEN': 'test_token', 'TELEGRAM_CHAT_ID': '123456'})
    def test_send_telegram_api_error(self):
        """Test handling of Telegram API error."""
        with patch('scheme_intel.notifier.requests.post') as mock_post:
            mock_post.side_effect = ConnectionError("API connection failed")
            
            with pytest.raises(TelegramError):
                send_telegram("Test message")
    
    @patch.dict('os.environ', {'TELEGRAM_BOT_TOKEN': 'test_token', 'TELEGRAM_CHAT_ID': '123456'})
    def test_send_telegram_timeout(self):
        """Test handling of request timeout."""
        with patch('scheme_intel.notifier.requests.post') as mock_post:
            mock_post.side_effect = Timeout("Request timeout")
            
            with pytest.raises(TelegramError):
                send_telegram("Test message")
    
    def test_send_telegram_custom_chat_ids(self):
        """Test sending with explicitly provided chat IDs."""
        with patch('scheme_intel.notifier.requests.post') as mock_post:
            mock_response = Mock()
            mock_response.raise_for_status = Mock()
            mock_post.return_value = mock_response
            
            with patch.dict('os.environ', {'TELEGRAM_BOT_TOKEN': 'test_token'}):
                result = send_telegram("Test", chat_ids=["111", "222"])
                
                assert result is True
                assert mock_post.call_count == 2


class TestValidateTelegramConfig:
    """Tests for Telegram configuration validation."""
    
    @patch.dict('os.environ', {'TELEGRAM_BOT_TOKEN': 'test_token', 'TELEGRAM_CHAT_ID': '123456'})
    def test_validate_valid_config(self):
        """Test validation of valid configuration."""
        result = validate_telegram_config()
        assert result is True
    
    @patch.dict('os.environ', {'TELEGRAM_BOT_TOKEN': 'test_token'}, clear=True)
    def test_validate_missing_chat_id(self):
        """Test validation when chat ID is missing."""
        result = validate_telegram_config()
        assert result is False
    
    @patch.dict('os.environ', {'TELEGRAM_CHAT_ID': '123456'}, clear=True)
    def test_validate_missing_token(self):
        """Test validation when token is missing."""
        result = validate_telegram_config()
        assert result is False
    
    @patch.dict('os.environ', {}, clear=True)
    def test_validate_empty_env(self):
        """Test validation with empty environment."""
        result = validate_telegram_config()
        assert result is False
