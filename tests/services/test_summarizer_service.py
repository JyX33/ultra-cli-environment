import pytest
from unittest.mock import MagicMock
from app.services.summarizer_service import summarize_content


def test_summarize_post_success(mocker):
    mock_response = {
        'choices': [
            {
                'message': {
                    'content': 'This is a concise summary of the article.'
                }
            }
        ]
    }
    
    mock_chat_completion = mocker.patch('openai.ChatCompletion.create')
    mock_chat_completion.return_value = mock_response
    
    content = "This is some long article text that needs to be summarized."
    result = summarize_content(content, "post")
    
    mock_chat_completion.assert_called_once_with(
        model="gpt-3.5-turbo",
        messages=[
            {"role": "system", "content": "Summarize the following article text concisely."},
            {"role": "user", "content": content}
        ]
    )
    
    assert result == "This is a concise summary of the article."


def test_summarize_comments_success(mocker):
    mock_response = {
        'choices': [
            {
                'message': {
                    'content': 'Community sentiment is positive with key discussion points.'
                }
            }
        ]
    }
    
    mock_chat_completion = mocker.patch('openai.ChatCompletion.create')
    mock_chat_completion.return_value = mock_response
    
    content = "Comment 1: Great article! Comment 2: I disagree with this point."
    result = summarize_content(content, "comments")
    
    mock_chat_completion.assert_called_once_with(
        model="gpt-3.5-turbo",
        messages=[
            {"role": "system", "content": "Summarize the following Reddit comments, capturing the overall community sentiment and key discussion points."},
            {"role": "user", "content": content}
        ]
    )
    
    assert result == "Community sentiment is positive with key discussion points."


def test_summarize_failure(mocker):
    mock_chat_completion = mocker.patch('openai.ChatCompletion.create')
    mock_chat_completion.side_effect = Exception("API call failed")
    
    content = "Some content to summarize"
    result = summarize_content(content, "post")
    
    assert result == "AI summary could not be generated."