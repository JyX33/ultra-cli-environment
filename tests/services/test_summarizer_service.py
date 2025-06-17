from unittest.mock import patch

from openai.types.chat import ChatCompletion, ChatCompletionMessage
from openai.types.chat.chat_completion import Choice

from app.services.summarizer_service import summarize_content


@patch.dict('os.environ', {'OPENAI_API_KEY': 'sk-test123456789abcdef'})
def test_summarize_post_success(mocker):
    # Mock the modern OpenAI client response
    mock_message = ChatCompletionMessage(role="assistant", content="This is a concise summary of the article.")
    mock_choice = Choice(
        index=0,
        message=mock_message,
        finish_reason="stop"
    )
    ChatCompletion(
        id="chatcmpl-test",
        choices=[mock_choice],
        created=1234567890,
        model="gpt-3.5-turbo",
        object="chat.completion"
    )

    # Mock the modern client method
    mock_chat_completion = mocker.patch('app.services.summarizer_service.SummarizerService.summarize_content')
    mock_chat_completion.return_value = "This is a concise summary of the article."

    content = "This is some long article text that needs to be summarized."
    result = summarize_content(content, "post")

    # Verify the legacy function works
    assert result == "This is a concise summary of the article."


@patch.dict('os.environ', {'OPENAI_API_KEY': 'sk-test123456789abcdef'})
def test_summarize_comments_success(mocker):
    # Mock the modern client method
    mock_chat_completion = mocker.patch('app.services.summarizer_service.SummarizerService.summarize_content')
    mock_chat_completion.return_value = "Community sentiment is positive with key discussion points."

    content = "Comment 1: Great article! Comment 2: I disagree with this point."
    result = summarize_content(content, "comments")

    # Verify the legacy function works
    assert result == "Community sentiment is positive with key discussion points."


@patch.dict('os.environ', {'OPENAI_API_KEY': 'sk-test123456789abcdef'})
def test_summarize_failure(mocker):
    # Mock the modern client method to raise an exception
    mock_chat_completion = mocker.patch('app.services.summarizer_service.SummarizerService.summarize_content')
    mock_chat_completion.side_effect = Exception("API call failed")

    content = "Some content to summarize"
    result = summarize_content(content, "post")

    # The legacy function should handle exceptions gracefully
    assert result == "AI summary could not be generated."
